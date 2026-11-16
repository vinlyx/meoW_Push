"""Exception hierarchy for :mod:`meow_push`.

Every exception carries an ``exit_code`` so the CLI can map failures onto stable
process exit codes without a long ``isinstance`` chain.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class MeoWError(Exception):
    """Base class for every error raised by this package."""

    exit_code = 1

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class MeoWConfigError(MeoWError):
    """Configuration file is missing, unreadable or contains invalid values."""

    exit_code = 5


class MeoWValidationError(MeoWError):
    """Caller supplied an argument the API would reject anyway."""

    exit_code = 2


class MeoWNetworkError(MeoWError):
    """The service could not be reached, or the connection timed out."""

    exit_code = 3


class MeoWAPIError(MeoWError):
    """The service answered with a non-success business status."""

    exit_code = 4

    def __init__(
        self,
        status: int,
        message: str,
        *,
        payload: Optional[Dict[str, Any]] = None,
        hint: str = "",
        retry_after: Optional[float] = None,
    ) -> None:
        super().__init__("[{0}] {1}".format(status, message))
        self.status = status
        self.reason = message
        self.payload = payload or {}
        self.hint = hint
        self.retry_after = retry_after


class MeoWNotFoundError(MeoWAPIError):
    """The nickname is not registered (business status 404)."""


class MeoWRateLimitError(MeoWAPIError):
    """Rate limit hit, either locally (client-side guard) or on the server."""

    exit_code = 6
