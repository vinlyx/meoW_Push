"""Tests for config loading, saving and the nickname prompt."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from meow_push import Config, MeoWConfigError, default_config_path


class ConfigTests(unittest.TestCase):
    def test_missing_file_yields_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = Config.load(path)
            self.assertEqual(config.nickname, "")
            self.assertEqual(config.base_url, "https://api.chuckfang.com")
            self.assertEqual(config.html_font_size, 48)
            self.assertEqual(config.html_width, 900)
            self.assertTrue(config.html_wrap)
            self.assertFalse(config.rate_limit)
            self.assertEqual(config.path, path)

    def test_roundtrip_and_permissions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "meow-push" / "config.json"
            saved = Config(nickname="testuser", default_category="构建").save(path)
            self.assertTrue(saved.exists())
            self.assertEqual(json.loads(saved.read_text(encoding="utf-8"))["nickname"], "testuser")
            loaded = Config.load(path)
            self.assertEqual(loaded.nickname, "testuser")
            self.assertEqual(loaded.default_category, "构建")
            if os.name != "nt":
                self.assertEqual(saved.stat().st_mode & 0o777, 0o600)

    def test_env_overrides_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            Config(nickname="from-file").save(path)
            with mock.patch.dict(
                os.environ, {"MEOW_NICKNAME": "from-env", "MEOW_TIMEOUT": "3.5"}, clear=True
            ):
                loaded = Config.load(path)
            self.assertEqual(loaded.nickname, "from-env")
            self.assertEqual(loaded.timeout, 3.5)

    def test_meow_config_env_changes_default_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = str(Path(tmp) / "custom.json")
            with mock.patch.dict(os.environ, {"MEOW_CONFIG": target}, clear=True):
                self.assertEqual(default_config_path(), Path(target))

    def test_html_defaults_roundtrip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            Config(
                html_font_size=32,
                html_width=760,
                html_css=".meow-html-push p{margin:0}",
                html_wrap=False,
                rate_limit=True,
            ).save(path)
            loaded = Config.load(path)
            self.assertEqual(loaded.html_font_size, 32)
            self.assertEqual(loaded.html_width, 760)
            self.assertEqual(loaded.html_css, ".meow-html-push p{margin:0}")
            self.assertFalse(loaded.html_wrap)
            self.assertTrue(loaded.rate_limit)

    def test_invalid_font_size_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"html_font_size": 2}), encoding="utf-8")
            with self.assertRaises(MeoWConfigError):
                Config.load(path)

    def test_invalid_json_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text("{oops", encoding="utf-8")
            with self.assertRaises(MeoWConfigError):
                Config.load(path)

    def test_invalid_timeout_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            path.write_text(json.dumps({"timeout": -1}), encoding="utf-8")
            with self.assertRaises(MeoWConfigError):
                Config.load(path)

    def test_ensure_nickname_prompts_once_and_saves(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            config = Config.load(path)
            nickname = config.ensure_nickname(
                prompt=True,
                input_fn=lambda _prompt="": "testuser",
                print_fn=lambda *_a, **_k: None,
            )
            self.assertEqual(nickname, "testuser")
            self.assertEqual(Config.load(path).nickname, "testuser")

    def test_ensure_nickname_without_prompt_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Config.load(Path(tmp) / "config.json")
            with self.assertRaises(MeoWConfigError) as ctx:
                config.ensure_nickname(prompt=False)
            self.assertIn("config set", str(ctx.exception))

    def test_ensure_nickname_uses_existing_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = Config(nickname="testuser")
            self.assertEqual(
                config.ensure_nickname(prompt=False, print_fn=lambda *_a: None), "testuser"
            )


if __name__ == "__main__":
    unittest.main()
