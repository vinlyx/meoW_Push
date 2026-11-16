"""Constants shared across the package."""

from __future__ import annotations

#: MeoW push service root. Both http:// and https:// are supported by the
#: service; https is the default because it keeps message bodies confidential.
DEFAULT_BASE_URL = "https://api.chuckfang.com"

#: Default socket timeout, in seconds.
REQUEST_TIMEOUT = 10.0

#: Default number of retries for transient failures (network / 429 / 5xx).
MAX_RETRIES = 2

#: Maximum number of characters allowed in a notification category.
CATEGORY_MAX_CHARS = 10

#: Local, best-effort mirror of the server side quota:
#: 1 message per 3 seconds, 15 per minute, 60 per hour.
RATE_RULES = ((3.0, 1), (60.0, 15), (3600.0, 60))

#: Business status codes returned in the JSON body (HTTP status is always 200).
STATUS_OK = 200
STATUS_BAD_REQUEST = 400
STATUS_FORBIDDEN = 403
STATUS_NOT_FOUND = 404
STATUS_RATE_LIMITED = 429
STATUS_SERVER_ERROR = 500
