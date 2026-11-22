"""Validation rules and null semantics of the travel requirement model."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from trippilot.domain.models import (
    Budget,
    BudgetScope,
    Currency,
    Interest,
    Pace,
    TripRequest,
)


class TestMissingSlots:
    """``missing_slots`` is the deterministic signal the clarification node
    will branch on, so it is specified precisely."""

    def test_empty_request_reports_every_required_slot(self) -> None:
        request = TripRequest()

        assert request.missing_slots() == ("destination", "start_date", "days")
        assert request.is_complete is False

    def test_none_means_unknown_not_a_default(self) -> None:
        """An unset traveller count must not be read as one person."""
        request = TripRequest()

        assert request.travelers is None
        assert request.budget is None
        assert "travelers" not in request.missing_slots()

    def test_an_end_date_satisfies_the_duration_slot(self) -> None:
        request = TripRequest(
            destination="长沙",
            start_date=date(2026, 10, 16),
            end_date=date(2026, 10, 18),
        )

        assert request.missing_slots() == ()
        assert request.is_complete is True
        assert request.days is None  # still unset; duration was derived, not stored

    def test_complete_request_has_no_missing_slots(self) -> None:
        request = TripRequest(destination="长沙", start_date=date(2026, 10, 16), days=3)

        assert request.missing_slots() == ()
        assert request.is_complete is True


class TestDateRules:
    def test_end_date_before_start_date_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="must not be earlier"):
            TripRequest(start_date=date(2026, 10, 18), end_date=date(2026, 10, 16))

    def test_single_day_trip_is_valid(self) -> None:
        request = TripRequest(start_date=date(2026, 10, 16), end_date=date(2026, 10, 16))

        assert request.derived_days == 1

    def test_day_count_contradicting_the_range_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="contradicts the range"):
            TripRequest(start_date=date(2026, 10, 16), end_date=date(2026, 10, 18), days=5)

    def test_day_count_matching_the_range_is_accepted(self) -> None:
        request = TripRequest(start_date=date(2026, 10, 16), end_date=date(2026, 10, 18), days=3)

        assert request.duration_days == 3

    def test_day_count_is_unconstrained_when_the_range_is_incomplete(self) -> None:
        request = TripRequest(start_date=date(2026, 10, 16), days=5)

        assert request.duration_days == 5
        assert request.derived_days is None

    @pytest.mark.parametrize("days", [0, -1, 31])
    def test_day_count_outside_supported_range_is_rejected(self, days: int) -> None:
        with pytest.raises(ValidationError):
            TripRequest(days=days)


class TestBudget:
    def test_amount_is_decimal_not_float(self) -> None:
        budget = Budget(amount=Decimal("2000.00"))

        assert isinstance(budget.amount, Decimal)
        assert budget.currency is Currency.CNY
        assert budget.scope is BudgetScope.TOTAL

    def test_negative_amount_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Budget(amount=Decimal("-1.00"))

    def test_more_than_two_decimal_places_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            Budget(amount=Decimal("10.001"))

    def test_scope_distinguishes_total_from_per_person(self) -> None:
        """ "预算 2000" is ambiguous; the model forces the ambiguity to be named."""
        total = Budget(amount=Decimal("2000.00"))
        per_person = Budget(amount=Decimal("2000.00"), scope=BudgetScope.PER_PERSON)

        assert total != per_person


class TestInterests:
    def test_duplicates_are_removed_preserving_first_seen_order(self) -> None:
        request = TripRequest(
            interests=(Interest.FOOD, Interest.CULTURE, Interest.FOOD, Interest.HISTORY)
        )

        assert request.interests == (Interest.FOOD, Interest.CULTURE, Interest.HISTORY)

    def test_plain_strings_are_coerced_to_enum_members(self) -> None:
        request = TripRequest(interests=("food", "culture"))

        assert request.interests == (Interest.FOOD, Interest.CULTURE)

    def test_unknown_interest_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TripRequest(interests=("shopping-spree",))

    def test_defaults_to_empty(self) -> None:
        assert TripRequest().interests == ()


class TestOtherFields:
    def test_pace_captures_a_relaxed_preference(self) -> None:
        request = TripRequest(pace="relaxed")

        assert request.pace is Pace.RELAXED

    @pytest.mark.parametrize("travelers", [0, 21])
    def test_traveller_count_outside_supported_range_is_rejected(self, travelers: int) -> None:
        with pytest.raises(ValidationError):
            TripRequest(travelers=travelers)

    def test_unknown_fields_are_rejected_rather_than_silently_dropped(self) -> None:
        """A typo in a future slot extractor must fail loudly.

        The misspelling is the point of the test, hence the targeted ignore.
        """
        with pytest.raises(ValidationError):
            TripRequest(destionation="长沙")  # type: ignore[call-arg]

    def test_a_realistic_request_parses_end_to_end(self) -> None:
        request = TripRequest(
            origin="深圳",
            destination="长沙",
            start_date=date(2026, 10, 16),
            days=3,
            budget=Budget(amount=Decimal("2000.00")),
            interests=("food", "culture"),
            travelers=2,
            pace="relaxed",
            notes="不要太赶",
        )

        assert request.is_complete is True
        assert request.duration_days == 3
        assert request.budget is not None
        assert request.budget.amount == Decimal("2000.00")
