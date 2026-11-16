"""HTTP client for the MeoW push service.

API reference: https://www.chuckfang.com/MeoW/api_doc.html

Key behaviours of the service that shape this client:

* Only **POST** is used here (the service also supports GET, but POST keeps
  long/HTML bodies out of URLs and access logs).
* The HTTP status is *always* 200; the real outcome lives in the JSON field
  ``status``. Hence the client inspects the body, not the HTTP code.
* ``msgType`` and ``htmlHeight`` are **query parameters**, never JSON fields;
  ``title`` / ``url`` / ``imgUrl`` / ``category`` belong in the JSON body.
* Quota: 1 message / 3 s, 15 / min, 60 / hour, 1000 / day.
"""

from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from .constants import (
    DEFAULT_BASE_URL,
    MAX_RETRIES,
    RATE_RULES,
    REQUEST_TIMEOUT,
    STATUS_BAD_REQUEST,
    STATUS_FORBIDDEN,
    STATUS_NOT_FOUND,
    STATUS_OK,
    STATUS_RATE_LIMITED,
    STATUS_SERVER_ERROR,
)
from .errors import (
    MeoWAPIError,
    MeoWNetworkError,
    MeoWNotFoundError,
    MeoWRateLimitError,
    MeoWValidationError,
)
from .validators import (
    clean_optional_text,
    validate_category,
    validate_html_height,
    validate_link,
    validate_message,
    validate_msg_type,
    validate_nickname,
)
from .version import __version__

USER_AGENT = "meow-push/{0} (+https://github.com/vinlyx/meowMsg)".format(__version__)

_STATUS_HINTS = {
    STATUS_BAD_REQUEST: "参数不合法：检查 title / msg / category 的长度与格式",
    STATUS_FORBIDDEN: "内容被内容策略拒绝，调整措辞后重试",
    STATUS_NOT_FOUND: "昵称未注册：核对配置中的 nickname（即专属推送链接里的那一段）",
    STATUS_RATE_LIMITED: (
        "触发 MeoW 频率限制：3 秒 1 条 / 每分钟 15 条 / 每小时 60 条 / 每天 1000 条"
    ),
    STATUS_SERVER_ERROR: "MeoW 服务端错误，稍后重试",
}


@dataclass
class SendResult:
    """Outcome of a successful (or dry-run) push."""

    ok: bool
    status: int
    message: str
    data: Any = None
    nickname: str = ""
    elapsed_ms: int = 0
    request: Optional[Dict[str, Any]] = None
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "ok": self.ok,
            "status": self.status,
            "message": self.message,
            "data": self.data,
            "nickname": self.nickname,
            "elapsed_ms": self.elapsed_ms,
        }
        if self.request is not None:
            result["request"] = self.request
        return result


class RateLimiter:
    """In-process, best-effort mirror of the server side quota.

    The service quota is per nickname and enforced server-side anyway; this
    guard exists only to fail fast (or wait briefly) instead of burning calls
    on avoidable 429s. State is not shared between processes.
    """

    def __init__(
        self,
        rules: Tuple[Tuple[float, int], ...] = RATE_RULES,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._rules = tuple((float(window), int(limit)) for window, limit in rules)
        self._hits: Deque[float] = deque(maxlen=1024)
        self._clock = clock
        self._sleeper = sleeper
        self._lock = Lock()

    def _delay_locked(self, now: float) -> float:
        delay = 0.0
        for window, limit in self._rules:
            recent = [stamp for stamp in self._hits if now - stamp < window]
            if len(recent) >= limit:
                # The oldest hit that still occupies a slot must expire first.
                oldest = recent[len(recent) - limit]
                delay = max(delay, window - (now - oldest))
        return delay

    def check(self) -> float:
        """Seconds to wait before the next send would be allowed."""
        with self._lock:
            return self._delay_locked(self._clock())

    def acquire(self, wait: bool = False, max_wait: float = 5.0) -> float:
        """Reserve a send slot. Returns the seconds actually slept."""
        waited = 0.0
        while True:
            with self._lock:
                delay = self._delay_locked(self._clock())
                if delay <= 0:
                    self._hits.append(self._clock())
                    return waited
            if not wait or waited + delay > max_wait:
                raise MeoWRateLimitError(
                    STATUS_RATE_LIMITED,
                    "本地频率限制：还需等待 {0:.1f} 秒".format(delay),
                    hint="用 --wait 等待，或稍后手动重试",
                    retry_after=delay,
                )
            self._sleeper(delay + 0.01)
            waited += delay + 0.01


class MeoWClient:
    """Thin, dependency-free client for one MeoW nickname."""

    def __init__(
        self,
        nickname: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = REQUEST_TIMEOUT,
        retries: int = MAX_RETRIES,
        rate_limit: bool = True,
        wait_on_rate_limit: bool = False,
        max_wait: float = 5.0,
        user_agent: Optional[str] = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.nickname = validate_nickname(nickname)
        self.base_url = _normalize_base_url(base_url)
        self.timeout = float(timeout)
        if self.timeout <= 0:
            raise MeoWValidationError("timeout 必须大于 0")
        self.retries = int(retries)
        if self.retries < 0:
            raise MeoWValidationError("retries 不能为负数")
        self.wait_on_rate_limit = bool(wait_on_rate_limit)
        self.max_wait = float(max_wait)
        self.user_agent = user_agent or USER_AGENT
        self._sleep = sleeper
        self._clock = clock
        self._limiter = (
            RateLimiter(clock=self._clock, sleeper=self._sleep) if rate_limit else None
        )

    # -- public API -------------------------------------------------------
    def send(
        self,
        msg: str,
        *,
        title: Optional[str] = None,
        url: Optional[str] = None,
        img_url: Optional[str] = None,
        category: Optional[str] = None,
        msg_type: str = "text",
        html_height: Optional[int] = None,
        dry_run: bool = False,
    ) -> SendResult:
        """Push one notification. Raises a :class:`MeoWError` subclass on failure."""
        message = validate_message(msg)
        clean_title = clean_optional_text(title, "title")
        clean_category = validate_category(category)
        mode = validate_msg_type(msg_type)
        height = validate_html_height(html_height, mode)
        link = validate_link(url, "url")
        icon = validate_link(img_url, "imgUrl")

        params: Dict[str, str] = {"msgType": mode}
        if height is not None:
            params["htmlHeight"] = str(height)

        body: Dict[str, Any] = {"msg": message}
        if clean_title:
            body["title"] = clean_title
        if link:
            body["url"] = link
        if icon:
            body["imgUrl"] = icon
        if clean_category:
            body["category"] = clean_category

        endpoint = self._build_endpoint(params)
        preview = {
            "method": "POST",
            "url": endpoint,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": self.user_agent,
            },
            "json": body,
        }

        if dry_run:
            return SendResult(
                ok=True,
                status=0,
                message="dry-run（未发送）",
                nickname=self.nickname,
                request=preview,
            )

        if self._limiter is not None:
            self._limiter.acquire(
                wait=self.wait_on_rate_limit, max_wait=self.max_wait
            )

        attempt = 0
        while True:
            started = self._clock()
            http_status, text = self._post(endpoint, body)
            elapsed_ms = int(round((self._clock() - started) * 1000))

            payload = _parse_payload(text)
            status = _int_or_none(payload.get("status")) if payload else None
            retryable = status in (STATUS_RATE_LIMITED, STATUS_SERVER_ERROR) or (
                payload is None and (http_status == 429 or http_status >= 500)
            )
            if retryable and attempt < self.retries:
                attempt += 1
                self._sleep(
                    self._backoff(attempt, rate_limited=status == STATUS_RATE_LIMITED)
                )
                continue

            if payload is None:
                raise MeoWAPIError(
                    http_status or -1,
                    "响应无法解析为 JSON：{0}".format(text[:200]),
                    payload=None,
                )
            if status is None:
                raise MeoWAPIError(
                    http_status or -1,
                    "响应缺少 status 字段：{0}".format(text[:200]),
                    payload=payload,
                )
            return self._result(status, payload, elapsed_ms)

    def build_request(
        self,
        msg: str,
        *,
        title: Optional[str] = None,
        url: Optional[str] = None,
        img_url: Optional[str] = None,
        category: Optional[str] = None,
        msg_type: str = "text",
        html_height: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Return the request that :meth:`send` would issue (no network I/O)."""
        return self.send(
            msg,
            title=title,
            url=url,
            img_url=img_url,
            category=category,
            msg_type=msg_type,
            html_height=html_height,
            dry_run=True,
        ).request or {}

    # -- internals --------------------------------------------------------
    def _build_endpoint(self, params: Dict[str, str]) -> str:
        path = urllib.parse.quote(self.nickname, safe="")
        endpoint = "{0}/{1}".format(self.base_url, path)
        query = urllib.parse.urlencode(params)
        return "{0}?{1}".format(endpoint, query) if query else endpoint

    def _post(self, url: str, body: Dict[str, Any]) -> Tuple[int, str]:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Accept": "application/json",
                "User-Agent": self.user_agent,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None) or response.getcode()
                return int(status), response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            # The service claims HTTP 200 always, but proxies/CDNs may not.
            try:
                text = exc.read().decode("utf-8", "replace")
            except OSError:
                text = ""
            return int(exc.code), text
        except urllib.error.URLError as exc:
            raise MeoWNetworkError(
                "无法连接 {0}：{1}".format(self.base_url, exc.reason)
            )
        except (socket.timeout, TimeoutError) as exc:
            raise MeoWNetworkError("请求超时（{0}s）：{1}".format(self.timeout, exc))
        except OSError as exc:
            raise MeoWNetworkError("网络错误：{0}".format(exc))

    def _result(
        self, status: int, payload: Dict[str, Any], elapsed_ms: int
    ) -> SendResult:
        message = str(payload.get("msg") or "")
        if status == STATUS_OK:
            return SendResult(
                ok=True,
                status=status,
                message=message or "发送成功",
                data=payload.get("data"),
                nickname=self.nickname,
                elapsed_ms=elapsed_ms,
                payload=payload,
            )
        hint = _STATUS_HINTS.get(status, "")
        if status == STATUS_NOT_FOUND:
            error_class = MeoWNotFoundError
        elif status == STATUS_RATE_LIMITED:
            error_class = MeoWRateLimitError
        else:
            error_class = MeoWAPIError
        raise error_class(status, message or "未知错误", payload=payload, hint=hint)

    def _backoff(self, attempt: int, *, rate_limited: bool = False) -> float:
        base = 2.0 if rate_limited else 0.8
        return min(base * (2 ** (attempt - 1)), 8.0)


# -- module level convenience ---------------------------------------------
_CLIENTS: Dict[Tuple[str, str, float, int], MeoWClient] = {}
_CLIENTS_LOCK = Lock()


def get_client(
    nickname: str,
    *,
    base_url: str = DEFAULT_BASE_URL,
    timeout: float = REQUEST_TIMEOUT,
    retries: int = MAX_RETRIES,
) -> MeoWClient:
    """Return a cached client so the rate limiter survives across calls."""
    key = (nickname, base_url.rstrip("/"), float(timeout), int(retries))
    with _CLIENTS_LOCK:
        client = _CLIENTS.get(key)
        if client is None:
            client = MeoWClient(
                nickname,
                base_url=base_url,
                timeout=timeout,
                retries=retries,
                wait_on_rate_limit=True,
            )
            _CLIENTS[key] = client
        return client


def send(
    msg: str,
    *,
    nickname: Optional[str] = None,
    config_path: Optional[str] = None,
    **options: Any
) -> SendResult:
    """One-liner push using the saved config.

    >>> from meow_push import send
    >>> send("构建完成", title="CI", category="告警")

    Extra keyword arguments are forwarded to :meth:`MeoWClient.send`
    (``title`` / ``url`` / ``img_url`` / ``category`` / ``msg_type`` /
    ``html_height`` / ``dry_run``), plus ``base_url`` / ``timeout`` / ``retries``
    overrides. This never prompts: a missing nickname raises
    :class:`MeoWConfigError`.
    """
    from .config import Config

    config = Config.load(config_path)
    nick = validate_nickname(nickname) if nickname else config.ensure_nickname(prompt=False)
    base_url = options.pop("base_url", None) or config.base_url
    timeout = options.pop("timeout", None) or config.timeout
    retries = options.pop("retries", None)
    if retries is None:
        retries = config.retries
    client = get_client(nick, base_url=base_url, timeout=timeout, retries=retries)
    return client.send(msg, **options)


def _normalize_base_url(value: str) -> str:
    url = str(value).strip().rstrip("/")
    lowered = url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise MeoWValidationError(
            "base_url 必须以 http:// 或 https:// 开头：{0!r}".format(value)
        )
    return url


def _parse_payload(text: str) -> Optional[Dict[str, Any]]:
    if not text or not text.strip():
        return None
    try:
        data = json.loads(text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _int_or_none(value: Any) -> Optional[int]:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
