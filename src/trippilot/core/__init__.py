"""Infrastructure shared by every layer: configuration, logging, errors.

``core`` sits at the bottom of the dependency graph and must not import from
``api``, ``agent``, ``tools``, ``repositories``, ``domain`` or ``schemas``.
"""
