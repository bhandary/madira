"""Errors a domain service raises. Callers map them to HTTP or tool JSON."""

from __future__ import annotations


class NotFound(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
