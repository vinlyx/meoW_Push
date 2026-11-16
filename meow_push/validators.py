"""Input validation shared by the client, the config layer and the CLI.

Validating locally is not about distrusting the server: MeoW answers every
request with HTTP 200 and puts the real outcome in ``status``, so a client-side
check produces a far better error message (and saves quota).
"""

from __future__ import annotations

from typing import Any, Optional

from .constants import CATEGORY_MAX_CHARS
from .errors import MeoWValidationError

MAX_NICKNAME_CHARS = 64
MSG_TYPES = ("text", "html")


def validate_nickname(value: Any) -> str:
    """Return a cleaned nickname or raise :class:`MeoWValidationError`."""
    if not isinstance(value, str):
        raise MeoWValidationError("nickname 必须是字符串")
    nickname = value.strip()
    if not nickname:
        raise MeoWValidationError("nickname 不能为空")
    if "/" in nickname or "\\" in nickname:
        raise MeoWValidationError("nickname 不能包含斜杠：{0!r}".format(nickname))
    if any(ord(char) < 32 or ord(char) == 127 for char in nickname):
        raise MeoWValidationError("nickname 不能包含换行或控制字符")
    if len(nickname) > MAX_NICKNAME_CHARS:
        raise MeoWValidationError(
            "nickname 过长（最多 {0} 个字符）".format(MAX_NICKNAME_CHARS)
        )
    return nickname


def validate_message(value: Any) -> str:
    """Return the message body unchanged (whitespace is meaningful for HTML)."""
    if not isinstance(value, str):
        raise MeoWValidationError("msg 必须是字符串")
    if not value.strip():
        raise MeoWValidationError("msg 不能为空")
    return value


def clean_optional_text(value: Any, name: str) -> Optional[str]:
    """Trim an optional string; blank strings collapse to ``None``."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise MeoWValidationError("{0} 必须是字符串".format(name))
    text = value.strip()
    return text or None


def validate_link(value: Any, name: str) -> Optional[str]:
    """Validate an http(s) link. Empty values collapse to ``None``."""
    link = clean_optional_text(value, name)
    if link is None:
        return None
    lowered = link.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise MeoWValidationError(
            "{0} 必须是 http/https 链接，当前为 {1!r}".format(name, link)
        )
    return link


def validate_category(value: Any) -> Optional[str]:
    """Validate the optional category (max 10 characters, no control chars)."""
    category = clean_optional_text(value, "category")
    if category is None:
        return None
    if any(ord(char) < 32 or ord(char) == 127 for char in category):
        raise MeoWValidationError("category 不能包含换行或控制字符")
    if len(category) > CATEGORY_MAX_CHARS:
        raise MeoWValidationError(
            "category 最多 {0} 个字符（当前 {1}）：{2!r}".format(
                CATEGORY_MAX_CHARS, len(category), category
            )
        )
    return category


def validate_msg_type(value: Any) -> str:
    if value is None:
        return "text"
    if not isinstance(value, str):
        raise MeoWValidationError("msgType 必须是字符串")
    mode = value.strip().lower()
    if mode not in MSG_TYPES:
        raise MeoWValidationError(
            "msgType 只能是 {0}，当前为 {1!r}".format(" 或 ".join(MSG_TYPES), value)
        )
    return mode


def validate_html_height(value: Any, msg_type: str) -> Optional[int]:
    """``htmlHeight`` is only meaningful when ``msgType=html``."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise MeoWValidationError("htmlHeight 必须是整数")
    if isinstance(value, float):
        if not value.is_integer():
            raise MeoWValidationError("htmlHeight 必须是整数")
        value = int(value)
    if isinstance(value, str) and value.strip().isdigit():
        value = int(value.strip())
    if not isinstance(value, int):
        raise MeoWValidationError("htmlHeight 必须是整数")
    if value <= 0:
        raise MeoWValidationError("htmlHeight 必须大于 0")
    if msg_type != "html":
        raise MeoWValidationError("htmlHeight 仅在 msgType=html 时有效")
    return value
