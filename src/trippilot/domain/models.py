"""Travel requirement domain model.

This is the *business* representation of what a traveller wants, expressed in
typed values rather than strings. It has no dependency on FastAPI, LangGraph,
SQLAlchemy or any external provider -- see AGENTS.md 4.1.

Null semantics
--------------
Every field is optional here and ``None`` means *the user has not told us yet*.
It never means "false", "zero" or "use the default". A missing slot and a slot
the user explicitly left open are different states, and the future
clarification flow (docs/architecture/state-model.md) needs to tell them apart.
Concretely: ``travelers=None`` means unknown, not "1 person"; ``budget=None``
means unpriced, not "free".

Scope
-----
This module currently models the *requirement* only. Itinerary/plan models,
their versioning, and persistence arrive with the repositories layer.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Slot names that must be filled before an itinerary can be produced.
#: ``days`` is satisfied by an explicit day count *or* by an ``end_date``.
REQUIRED_SLOTS: Final[tuple[str, ...]] = ("destination", "start_date", "days")

MAX_TRIP_DAYS: Final[int] = 30


class Currency(StrEnum):
    """Only CNY is in scope for domestic trips.

    Other currencies are added when the product supports them, not in advance.
    """

    CNY = "CNY"


class BudgetScope(StrEnum):
    """Whether a budget covers the whole party or each traveller.

    This distinction is a real source of conflicting requirements: "预算 2000"
    is ambiguous, and reading it as per-person when the user meant total
    changes the itinerary materially.
    """

    TOTAL = "total"
    PER_PERSON = "per_person"


class Interest(StrEnum):
    """What the traveller wants to spend time on."""

    FOOD = "food"
    CULTURE = "culture"
    HISTORY = "history"
    NATURE = "nature"
    PHOTOGRAPHY = "photography"
    SHOPPING = "shopping"
    NIGHTLIFE = "nightlife"
    FAMILY = "family"
    ADVENTURE = "adventure"


class Pace(StrEnum):
    """How densely packed each day should be."""

    RELAXED = "relaxed"
    BALANCED = "balanced"
    PACKED = "packed"


class Budget(BaseModel):
    """A money amount with an explicit currency and scope.

    ``Decimal`` rather than ``float``: money must not accumulate binary
    rounding error, and ``ge=0`` rejects the nonsensical negative budget.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    amount: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    currency: Currency = Currency.CNY
    scope: BudgetScope = BudgetScope.TOTAL


class TripRequest(BaseModel):
    """What a traveller has told us so far about their trip."""

    model_config = ConfigDict(extra="forbid", validate_default=True)

    origin: str | None = Field(
        default=None, min_length=1, max_length=64, description="Departure city."
    )
    destination: str | None = Field(
        default=None, min_length=1, max_length=64, description="Destination city."
    )
    start_date: date | None = Field(default=None, description="First day of the trip.")
    end_date: date | None = Field(default=None, description="Last day, inclusive.")
    days: int | None = Field(
        default=None, ge=1, le=MAX_TRIP_DAYS, description="Trip length in days."
    )
    budget: Budget | None = None
    interests: tuple[Interest, ...] = Field(
        default=(), description="Deduplicated, order preserved."
    )
    travelers: int | None = Field(default=None, ge=1, le=20)
    pace: Pace | None = None
    notes: str | None = Field(
        default=None,
        max_length=500,
        description="Free-form remarks. Not parsed; kept so nothing is silently dropped.",
    )

    @model_validator(mode="after")
    def _check_dates_are_ordered(self) -> Self:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError(
                f"end_date ({self.end_date}) must not be earlier than "
                f"start_date ({self.start_date})"
            )
        return self

    @model_validator(mode="after")
    def _check_duration_agrees_with_dates(self) -> Self:
        """Reject a day count that contradicts the date range.

        Raising here is deliberate for now: this layer states facts, it does not
        negotiate. The clarification flow will detect this disagreement
        *before* validation and ask the traveller which value wins, so a
        contradiction should never reach the domain model in normal operation.
        """
        derived = self.derived_days
        if derived is not None and self.days is not None and self.days != derived:
            raise ValueError(
                f"days ({self.days}) contradicts the range "
                f"{self.start_date}..{self.end_date} ({derived} days)"
            )
        return self

    @field_validator("interests")
    @classmethod
    def _deduplicate_interests(cls, value: tuple[Interest, ...]) -> tuple[Interest, ...]:
        # dict.fromkeys preserves first-seen order while removing repeats.
        return tuple(dict.fromkeys(value))

    @property
    def derived_days(self) -> int | None:
        """Trip length implied by the date range, if both ends are known."""
        if self.start_date is None or self.end_date is None:
            return None
        return (self.end_date - self.start_date).days + 1

    @property
    def duration_days(self) -> int | None:
        """Best available trip length, preferring the explicit value."""
        return self.days if self.days is not None else self.derived_days

    @property
    def is_complete(self) -> bool:
        """True when nothing required is missing."""
        return not self.missing_slots()

    def missing_slots(self) -> tuple[str, ...]:
        """Names of required slots the traveller has not supplied yet.

        Deliberately rule-based, not LLM-driven: this is the signal the
        clarification node will branch on, and it must be deterministic and
        unit-testable.
        """
        missing: list[str] = []
        if self.destination is None:
            missing.append("destination")
        if self.start_date is None:
            missing.append("start_date")
        if self.duration_days is None:
            missing.append("days")
        return tuple(missing)
