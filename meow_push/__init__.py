"""meow_push - push notifications to a HarmonyOS phone through MeoW.

Quick start::

    from meow_push import send
    send("构建完成", title="CI", category="告警")

API reference: https://www.chuckfang.com/MeoW/api_doc.html
"""

from __future__ import annotations

from .client import MeoWClient, RateLimiter, SendResult, get_client, send
from .config import Config, default_config_path
from .errors import (
    MeoWAPIError,
    MeoWConfigError,
    MeoWError,
    MeoWNetworkError,
    MeoWNotFoundError,
    MeoWRateLimitError,
    MeoWValidationError,
)
from .validators import validate_nickname
from .version import __version__

__all__ = [
    "Config",
    "MeoWAPIError",
    "MeoWClient",
    "MeoWConfigError",
    "MeoWError",
    "MeoWNetworkError",
    "MeoWNotFoundError",
    "MeoWRateLimitError",
    "MeoWValidationError",
    "RateLimiter",
    "SendResult",
    "__version__",
    "default_config_path",
    "get_client",
    "send",
    "validate_nickname",
]
