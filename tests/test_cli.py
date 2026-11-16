"""End-to-end tests for the CLI against a local mock endpoint."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from meow_push import Config
from meow_push.cli import main
from tests.support import MockMeoW


def run_cli(argv):
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = main(argv)
    return code, buffer.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def _write_config(self, server, **overrides):
        config = Config(nickname="Vinlyx", base_url=server.base_url, **overrides)
        return config.save(self.tmp / "config.json")

    def test_send_human_output(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, output = run_cli(
                ["--config", str(path), "send", "hello", "-t", "标题", "-c", "测试"]
            )
            self.assertEqual(code, 0)
            self.assertIn("已发送", output)
            self.assertEqual(len(server.requests), 1)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body["title"], "标题")
            self.assertEqual(body["category"], "测试")

    def test_send_json_output(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, output = run_cli(["--config", str(path), "--json", "send", "hello"])
            self.assertEqual(code, 0)
            payload = json.loads(output)
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["status"], 200)
            self.assertEqual(payload["nickname"], "Vinlyx")

    def test_global_option_after_subcommand(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, output = run_cli(["send", "hello", "--config", str(path), "--json"])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output)["ok"])

    def test_shorthand_without_subcommand(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, output = run_cli(["--config", str(path), "直接发送"])
            self.assertEqual(code, 0)
            self.assertIn("已发送", output)

    def test_stdin_message(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            with mock.patch("sys.stdin", io.StringIO("来自 stdin 的消息")):
                code, _ = run_cli(["--config", str(path), "send", "--stdin", "-t", "管道"])
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body["msg"], "来自 stdin 的消息")

    def test_dry_run_does_not_send(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, output = run_cli(["--config", str(path), "send", "hi", "--dry-run"])
            self.assertEqual(code, 0)
            self.assertEqual(server.requests, [])
            self.assertIn("POST", output)

    def test_html_flags_reach_the_request(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(
                ["--config", str(path), "send", "<b>hi</b>", "--html", "--html-height", "320"]
            )
            self.assertEqual(code, 0)
            self.assertIn("msgType=html", server.requests[0]["path"])
            self.assertIn("htmlHeight=320", server.requests[0]["path"])

    def test_missing_nickname_exits_with_config_error(self) -> None:
        path = self.tmp / "empty.json"
        config = Config().save(path)
        self.assertTrue(config.exists())
        code, _ = run_cli(
            ["--config", str(path), "send", "hi", "--no-prompt", "--base-url", "http://127.0.0.1:1"]
        )
        self.assertEqual(code, 5)

    def test_api_error_exit_code(self) -> None:
        with MockMeoW(response={"status": 403, "data": False, "msg": "内容策略禁止发送"}) as server:
            path = self._write_config(server)
            code, _ = run_cli(["--config", str(path), "send", "hi", "--retries", "0"])
            self.assertEqual(code, 4)

    def test_api_error_json_payload(self) -> None:
        with MockMeoW(response={"status": 404, "data": False, "msg": "昵称未注册"}) as server:
            path = self._write_config(server)
            code, output = run_cli(["--config", str(path), "--json", "send", "hi", "--retries", "0"])
            self.assertEqual(code, 4)
            payload = json.loads(output)
            self.assertFalse(payload["ok"])
            self.assertEqual(payload["status"], 404)
            self.assertIn("nickname", payload["hint"])

    def test_config_set_and_show(self) -> None:
        path = self.tmp / "cfg.json"
        code, _ = run_cli(["--config", str(path), "config", "set", "Vinlyx"])
        self.assertEqual(code, 0)
        code, output = run_cli(["--config", str(path), "config", "show"])
        self.assertEqual(code, 0)
        payload = json.loads(output)
        self.assertEqual(payload["nickname"], "Vinlyx")
        self.assertEqual(payload["config_path"], str(path))

    def test_config_path(self) -> None:
        path = self.tmp / "cfg.json"
        code, output = run_cli(["--config", str(path), "config", "path"])
        self.assertEqual(code, 0)
        self.assertEqual(output.strip(), str(path))

    def test_test_command_sends_marker_message(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(["--config", str(path), "test"])
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertIn("测试消息", body["msg"])
            self.assertEqual(body["category"], "测试")

    def test_font_size_and_css_flags(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(
                [
                    "--config",
                    str(path),
                    "send",
                    "<b>x</b>",
                    "--html",
                    "--font-size",
                    "28",
                    "--css",
                    ".meow-html-push p{color:#c00}",
                ]
            )
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertIn("font-size:28px", body["msg"])
            self.assertIn("color:#c00", body["msg"])
            self.assertIn("htmlHeight=220", server.requests[0]["path"])

    def test_width_flag_reaches_wrapper(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(
                ["--config", str(path), "send", "x", "--html", "--width", "700"]
            )
            self.assertEqual(code, 0)
            message = json.loads(server.requests[0]["body"].decode("utf-8"))["msg"]
            self.assertIn("width:700px", message)

    def test_rate_limit_flag_is_accepted(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(["--config", str(path), "send", "x", "--rate-limit"])
            self.assertEqual(code, 0)

    def test_no_html_wrap_flag(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            code, _ = run_cli(
                ["--config", str(path), "send", "<b>x</b>", "--html", "--no-html-wrap"]
            )
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body["msg"], "<b>x</b>")

    def test_css_file_is_loaded(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server)
            css_file = self.tmp / "custom.css"
            css_file.write_text(".meow-html-push p{font-size:60px}", encoding="utf-8")
            code, _ = run_cli(
                ["--config", str(path), "send", "x", "--html", "--css", "@{0}".format(css_file)]
            )
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertIn("font-size:60px", body["msg"])

    def test_config_html_defaults_are_applied(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(
                server, html_font_size=32, html_css=".meow-html-push p{margin:0}"
            )
            code, _ = run_cli(["--config", str(path), "send", "x", "--html"])
            self.assertEqual(code, 0)
            message = json.loads(server.requests[0]["body"].decode("utf-8"))["msg"]
            self.assertIn("font-size:32px", message)
            self.assertIn("margin:0", message)

    def test_config_defaults_are_applied(self) -> None:
        with MockMeoW() as server:
            path = self._write_config(server, default_category="定时任务", default_title="默认标题")
            code, _ = run_cli(["--config", str(path), "send", "hi"])
            self.assertEqual(code, 0)
            body = json.loads(server.requests[0]["body"].decode("utf-8"))
            self.assertEqual(body["title"], "默认标题")
            self.assertEqual(body["category"], "定时任务")


if __name__ == "__main__":
    unittest.main()
