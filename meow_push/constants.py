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

#: Default base font size for HTML notifications, in CSS px.
#: Measured on harmony devices: a bare snippet renders around 10px, and 48px
#: is the size the user found comfortable (~4.8x).
DEFAULT_HTML_FONT_SIZE = 48

#: Default content width for HTML notifications, in CSS px.
#: A 48px line of ~24 mixed CJK/ASCII characters measured ~1000px wide before
#: wrapping, so 900px keeps roughly 18 CJK characters per line without the
#: card overflowing horizontally. ``max-width:100%`` keeps narrow viewports safe.
DEFAULT_HTML_WIDTH = 900

#: Lower/upper bounds accepted for the HTML base font size.
HTML_FONT_SIZE_MIN = 8
HTML_FONT_SIZE_MAX = 200

#: Lower/upper bounds accepted for the HTML content width.
HTML_WIDTH_MIN = 200
HTML_WIDTH_MAX = 2400

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
