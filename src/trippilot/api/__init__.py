"""HTTP layer: routing, request validation, response assembly, error mapping.

Routes stay thin. Business rules belong in ``domain/``; anything that talks to
an external system belongs in ``tools/`` or ``repositories/``.
"""
