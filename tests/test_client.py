"""Tests for request construction, error mapping and retries."""

from __future__ import annotations

import json
import unittest
import urllib.parse

from meow_push import (
    MeoWAPIError,
    MeoWClient,
    MeoWNetworkError,
    MeoWNotFoundError,
    MeoWRateLimitError,
    MeoWValidationError,
    RateLimiter,
)
from meow_push.constants import CATEGORY_MAX_CHARS
from tests.support import MockMeoW


class SendRequestTests(unittest.TestCase):
    def test_posts_json_to_nickname_endpoint(self) -> None:
        with MockMeoW() as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False)
            result = client.send(
                "构建完成",
                title="CI",
                url="https://example.com/run/1",
                img_url="https://example.com/icon.png",
                category="告警",
            )
            self.assertTrue(result.ok)
            self.assertEqual(result.status, 200)
            self.assertEqual(result.nickname, "Vinlyx")
            self.assertEqual(result.message, "发送成功")

            request = server.requests[0]
            self.assertEqual(request["method"], "POST")
            parts = urllib.parse.urlsplit(request["path"])
            self.assertEqual(parts.path, "/Vinlyx")
            query = urllib.parse.parse_qs(parts.query)
            self.assertEqual(query["msgType"], ["text"])
            self.assertNotIn("htmlHeight", query)

            body = json.loads(request["body"].decode("utf-8"))
            self.assertEqual(body["msg"], "构建完成")
            self.assertEqual(body["title"], "CI")
            self.assertEqual(body["url"], "https://example.com/run/1")
            self.assertEqual(body["imgUrl"], "https://example.com/icon.png")
            self.assertEqual(body["category"], "告警")
            self.assertTrue(request["headers"]["Content-Type"].startswith("application/json"))

    def test_html_mode_keeps_body_unencoded(self) -> None:
        with MockMeoW() as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False)
            html = "<p><b>欢迎</b>，这是 <i>HTML</i></p>"
            client.send(html, title="系统", msg_type="html", html_height=350)

            parts = urllib.parse.urlsplit(server.requests[0]["path"])
            query = urllib.parse.parse_qs(parts.query)
            self.assertEqual(query["msgType"], ["html"])
            self.assertEqual(query["htmlHeight"], ["350"])
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            # The snippet is wrapped, but never URL-encoded or escaped.
            self.assertIn(html, body["msg"])

    def test_nickname_is_percent_encoded_in_path(self) -> None:
        with MockMeoW() as server:
            MeoWClient("Vinlyx 测试", base_url=server.base_url, rate_limit=False).send("hi")
            path = urllib.parse.urlsplit(server.requests[0]["path"]).path
            self.assertEqual(urllib.parse.unquote(path), "/Vinlyx 测试")

    def test_optional_fields_are_omitted(self) -> None:
        with MockMeoW() as server:
            MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False).send("hi")
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body, {"msg": "hi"})

    def test_dry_run_skips_network(self) -> None:
        client = MeoWClient("Vinlyx", base_url="http://127.0.0.1:1", rate_limit=False)
        result = client.send("hi", dry_run=True, category="测试")
        self.assertEqual(result.status, 0)
        self.assertEqual(result.request["url"], "http://127.0.0.1:1/Vinlyx?msgType=text")
        self.assertEqual(result.request["json"]["category"], "测试")

    def test_build_request_matches_send(self) -> None:
        client = MeoWClient("Vinlyx", base_url="http://127.0.0.1:1", rate_limit=False)
        request = client.build_request("hi", title="t", msg_type="html", html_height=200)
        self.assertEqual(request["method"], "POST")
        self.assertIn("htmlHeight=200", request["url"])
        self.assertEqual(request["json"]["title"], "t")


class HtmlStylingTests(unittest.TestCase):
    def _client(self, server, **kwargs):
        return MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False, **kwargs)

    def test_default_wrap_sets_large_font_width_and_height(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("<b>完成</b>", msg_type="html")
            request = server.requests[0]
            body = json.loads(request["body"].decode("utf-8"))
            self.assertIn('class="meow-html-push"', body["msg"])
            self.assertIn("font-size:48px", body["msg"])
            self.assertIn("width:900px", body["msg"])
            self.assertIn("max-width:100%", body["msg"])
            self.assertIn("<b>完成</b>", body["msg"])
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(request["path"]).query)
            self.assertEqual(query["htmlHeight"], ["370"])

    def test_style_block_trails_content_for_preview(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("通知正文", msg_type="html")
            message = json.loads(server.requests[0]["body"].decode("utf-8"))["msg"]
            # The collapsed preview reads from the head: content must come first.
            self.assertLess(message.index("通知正文"), message.index("<style>"))

    def test_width_can_be_overridden(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("x", msg_type="html", html_width=720)
            message = json.loads(server.requests[0]["body"].decode("utf-8"))["msg"]
            self.assertIn("width:720px", message)

    def test_wrap_can_be_disabled(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("<b>完成</b>", msg_type="html", html_wrap=False)
            request = server.requests[0]
            body = json.loads(request["body"].decode("utf-8"))
            self.assertEqual(body["msg"], "<b>完成</b>")
            self.assertNotIn("htmlHeight", request["path"])

    def test_font_size_override_and_css_appended_last(self) -> None:
        with MockMeoW() as server:
            css = ".meow-html-push p { color: #c00; }"
            self._client(server).send("x", msg_type="html", html_font_size=72, html_css=css)
            request = server.requests[0]
            body = json.loads(request["body"].decode("utf-8"))
            self.assertIn("font-size:72px", body["msg"])
            self.assertIn(css, body["msg"])
            self.assertGreater(body["msg"].index(css), body["msg"].index("meow-html-push h1"))
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(request["path"]).query)
            self.assertEqual(query["htmlHeight"], ["560"])

    def test_explicit_height_wins_over_adaptive_default(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("x", msg_type="html", html_height=500)
            self.assertIn("htmlHeight=500", server.requests[0]["path"])

    def test_full_document_is_left_untouched(self) -> None:
        doc = "<!DOCTYPE html><html><body><p>x</p></body></html>"
        with MockMeoW() as server:
            self._client(server).send(doc, msg_type="html")
            request = server.requests[0]
            body = json.loads(request["body"].decode("utf-8"))
            self.assertEqual(body["msg"], doc)
            self.assertNotIn("htmlHeight", request["path"])

    def test_text_mode_is_never_wrapped(self) -> None:
        with MockMeoW() as server:
            self._client(server).send("<b>x</b>")
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body["msg"], "<b>x</b>")

    def test_font_size_is_bounded(self) -> None:
        client = MeoWClient("Vinlyx", rate_limit=False)
        for size in (4, 400):
            with self.assertRaises(MeoWValidationError):
                client.send("x", msg_type="html", html_font_size=size)

    def test_width_is_bounded(self) -> None:
        client = MeoWClient("Vinlyx", rate_limit=False)
        for width in (100, 5000):
            with self.assertRaises(MeoWValidationError):
                client.send("x", msg_type="html", html_width=width)


class ErrorMappingTests(unittest.TestCase):
    def test_business_404_maps_to_not_found(self) -> None:
        with MockMeoW(response={"status": 404, "data": False, "msg": "昵称未注册"}) as server:
            client = MeoWClient("nobody", base_url=server.base_url, rate_limit=False, retries=0)
            with self.assertRaises(MeoWNotFoundError) as ctx:
                client.send("hi")
            self.assertEqual(ctx.exception.status, 404)
            self.assertIn("昵称", ctx.exception.hint)
            self.assertEqual(ctx.exception.exit_code, 4)

    def test_business_403_maps_to_api_error(self) -> None:
        with MockMeoW(response={"status": 403, "data": False, "msg": "内容策略禁止发送"}) as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False, retries=0)
            with self.assertRaises(MeoWAPIError) as ctx:
                client.send("hi")
            self.assertEqual(ctx.exception.status, 403)

    def test_rate_limited_is_retried_then_raised(self) -> None:
        with MockMeoW(response={"status": 429, "data": False, "msg": "频率超限"}) as server:
            client = MeoWClient(
                "Vinlyx",
                base_url=server.base_url,
                rate_limit=False,
                retries=1,
                sleeper=lambda _seconds: None,
            )
            with self.assertRaises(MeoWRateLimitError):
                client.send("hi")
            self.assertEqual(len(server.requests), 2)

    def test_server_error_is_retried(self) -> None:
        with MockMeoW(response={"status": 500, "data": False, "msg": "boom"}) as server:
            client = MeoWClient(
                "Vinlyx",
                base_url=server.base_url,
                rate_limit=False,
                retries=2,
                sleeper=lambda _seconds: None,
            )
            with self.assertRaises(MeoWAPIError):
                client.send("hi")
            self.assertEqual(len(server.requests), 3)

    def test_bad_request_is_not_retried(self) -> None:
        with MockMeoW(response={"status": 400, "data": False, "msg": "分类名不能超过10个字"}) as server:
            client = MeoWClient(
                "Vinlyx",
                base_url=server.base_url,
                rate_limit=False,
                retries=2,
                sleeper=lambda _seconds: None,
            )
            with self.assertRaises(MeoWAPIError):
                client.send("hi")
            self.assertEqual(len(server.requests), 1)

    def test_non_json_response_surfaces_http_status(self) -> None:
        with MockMeoW(raw=b"<html>bad gateway</html>", status=502) as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False, retries=0)
            with self.assertRaises(MeoWAPIError) as ctx:
                client.send("hi")
            self.assertIn("502", str(ctx.exception))
            self.assertIn("JSON", str(ctx.exception))

    def test_response_missing_status(self) -> None:
        with MockMeoW(response={"data": True}) as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url, rate_limit=False)
            with self.assertRaises(MeoWAPIError) as ctx:
                client.send("hi")
            self.assertIn("status", str(ctx.exception))

    def test_network_error(self) -> None:
        client = MeoWClient(
            "Vinlyx", base_url="http://127.0.0.1:1", timeout=1.0, retries=0, rate_limit=False
        )
        with self.assertRaises(MeoWNetworkError):
            client.send("hi")


class ValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = MeoWClient("Vinlyx", base_url="http://127.0.0.1:1", rate_limit=False)

    def test_blank_message_is_rejected(self) -> None:
        with self.assertRaises(MeoWValidationError):
            self.client.send("   ")

    def test_category_too_long_is_rejected(self) -> None:
        with self.assertRaises(MeoWValidationError) as ctx:
            self.client.send("hi", category="x" * (CATEGORY_MAX_CHARS + 1))
        self.assertIn("10", str(ctx.exception))

    def test_category_with_newline_is_rejected(self) -> None:
        with self.assertRaises(MeoWValidationError):
            self.client.send("hi", category="a\nb")

    def test_blank_category_collapses_to_none(self) -> None:
        result = self.client.send("hi", category="   ", dry_run=True)
        self.assertNotIn("category", result.request["json"])

    def test_non_http_link_is_rejected(self) -> None:
        with self.assertRaises(MeoWValidationError):
            self.client.send("hi", url="example.com")

    def test_unknown_msg_type_is_rejected(self) -> None:
        with self.assertRaises(MeoWValidationError):
            self.client.send("hi", msg_type="markdown")

    def test_html_height_requires_html_mode(self) -> None:
        with self.assertRaises(MeoWValidationError):
            self.client.send("hi", html_height=300)

    def test_invalid_nickname_is_rejected(self) -> None:
        for nickname in ("", "a/b", "a\\b", "bad\nname"):
            with self.assertRaises(MeoWValidationError):
                MeoWClient(nickname, rate_limit=False)


class RateLimiterTests(unittest.TestCase):
    def test_second_call_inside_window_is_blocked(self) -> None:
        now = [1000.0]
        limiter = RateLimiter(rules=((3.0, 1),), clock=lambda: now[0], sleeper=lambda _s: None)
        limiter.acquire()
        with self.assertRaises(MeoWRateLimitError) as ctx:
            limiter.acquire()
        self.assertGreater(ctx.exception.retry_after, 0)

        now[0] += 3.1
        limiter.acquire()  # allowed again

    def test_wait_mode_sleeps_instead_of_raising(self) -> None:
        now = [1000.0]
        slept = []

        def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        limiter = RateLimiter(rules=((3.0, 1),), clock=lambda: now[0], sleeper=fake_sleep)
        limiter.acquire()
        waited = limiter.acquire(wait=True, max_wait=5.0)
        self.assertGreater(waited, 0)
        self.assertEqual(len(slept), 1)

    def test_minute_quota_is_tracked(self) -> None:
        now = [0.0]
        limiter = RateLimiter(
            rules=((60.0, 3),), clock=lambda: now[0], sleeper=lambda _s: None
        )
        for _ in range(3):
            limiter.acquire()
            now[0] += 1.0
        with self.assertRaises(MeoWRateLimitError):
            limiter.acquire()

    def test_client_does_not_rate_limit_by_default(self) -> None:
        with MockMeoW() as server:
            client = MeoWClient("Vinlyx", base_url=server.base_url)
            client.send("第一条")
            client.send("第二条")  # 会员账号无配额，默认不做本地限流
            self.assertEqual(len(server.requests), 2)


if __name__ == "__main__":
    unittest.main()
