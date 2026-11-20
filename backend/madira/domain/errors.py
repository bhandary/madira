"""Errors a domain service raises. Callers map them to HTTP or tool JSON."""

from __future__ import annotations


class NotFound(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class Unavailable(Exception):
    """A fixture-backed tool was called while the model is live."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class DraftFailed(Exception):
    """A structured draft failed validation, or the live model did not answer."""

    def __init__(self, message: str, status: int = 422) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


def require_demo(feature: str) -> None:
    """Stop fixture work when a provider key has taken the model out of demo mode."""
    from madira.tenancy import demo_posture

    if demo_posture():
        return
    raise Unavailable(f"{feature} has no live backend yet. Demo fixtures are not used when the model is live.")
