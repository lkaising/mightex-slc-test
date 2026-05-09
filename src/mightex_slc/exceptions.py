"""
Exception hierarchy for the Mightex SLC LED controller.

All exceptions inherit from :class:`MightexError` so callers can catch
broadly (``except MightexError``) or narrowly (``except MightexTimeoutError``).
"""


class MightexError(Exception):
    """Base exception for all Mightex SLC errors."""


class MightexConnectionError(MightexError):
    """Raised when the serial connection is unavailable or fails to open."""


class MightexTimeoutError(MightexError):
    """Raised when the controller does not respond within the expected window."""


class CommandError(MightexError):
    """Raised when the controller returns an error response (``#!``, ``#?``, etc.)."""


class ValidationError(MightexError):
    """Raised when an argument fails pre-send validation."""
