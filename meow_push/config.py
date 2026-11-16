"""Configuration loading, saving and the first-use nickname prompt.

Design notes
------------
The config lives *outside* the repository by default
(``~/.config/meow-push/config.json`` on Linux/WSL/macOS,
``%APPDATA%\\meow-push\\config.json`` on Windows), so nothing sensitive can be
committed by accident. ``--config`` / ``MEOW_CONFIG`` allow a per-project file
when that is more convenient; such a file is covered by ``.gitignore`` too.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

from .constants import DEFAULT_BASE_URL, MAX_RETRIES, REQUEST_TIMEOUT
from .errors import MeoWConfigError, MeoWError
from .validators import validate_nickname

APP_DIR_NAME = "meow-push"
CONFIG_FILE_NAME = "config.json"


def default_config_path(environ: Optional[Mapping[str, str]] = None) -> Path:
    """Return the platform specific config path, honouring ``MEOW_CONFIG``."""
    env = os.environ if environ is None else environ
    override = env.get("MEOW_CONFIG")
    if override:
        return Path(override).expanduser()
    if os.name == "nt":
        base = env.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_DIR_NAME / CONFIG_FILE_NAME
    xdg = env.get("XDG_CONFIG_HOME")
    base_dir = Path(xdg).expanduser() if xdg else Path.home() / ".config"
    return base_dir / APP_DIR_NAME / CONFIG_FILE_NAME


@dataclass
class Config:
    """Runtime configuration. Unknown keys in the file are ignored."""

    nickname: str = ""
    base_url: str = DEFAULT_BASE_URL
    timeout: float = REQUEST_TIMEOUT
    retries: int = MAX_RETRIES
    default_title: Optional[str] = None
    default_category: Optional[str] = None
    path: Optional[Path] = field(default=None, repr=False, compare=False)

    # -- construction -----------------------------------------------------
    @classmethod
    def load(cls, path: Optional[Any] = None) -> "Config":
        """Load config from *path* (default: platform path). Missing file is OK."""
        target = Path(path).expanduser() if path else default_config_path()
        config = cls(path=target)
        if target.is_file():
            try:
                raw = target.read_text(encoding="utf-8")
            except OSError as exc:
                raise MeoWConfigError("无法读取配置文件 {0}：{1}".format(target, exc))
            try:
                data = json.loads(raw)
            except ValueError as exc:
                raise MeoWConfigError(
                    "配置文件不是合法 JSON：{0}（{1}）".format(target, exc)
                )
            if not isinstance(data, dict):
                raise MeoWConfigError("配置文件顶层必须是 JSON 对象：{0}".format(target))
            config = cls.from_dict(data, path=target)
        return config.apply_env()

    @classmethod
    def from_dict(cls, data: Dict[str, Any], path: Optional[Path] = None) -> "Config":
        config = cls(path=path)
        nickname = data.get("nickname")
        if nickname:
            config.nickname = str(nickname).strip()
        base_url = data.get("base_url")
        if base_url:
            config.base_url = _clean_base_url(str(base_url), path)
        timeout = data.get("timeout")
        if timeout is not None:
            try:
                config.timeout = float(timeout)
            except (TypeError, ValueError):
                raise MeoWConfigError("timeout 必须是数字：{0!r}".format(timeout))
            if config.timeout <= 0:
                raise MeoWConfigError("timeout 必须大于 0：{0!r}".format(timeout))
        retries = data.get("retries")
        if retries is not None:
            try:
                config.retries = int(retries)
            except (TypeError, ValueError):
                raise MeoWConfigError("retries 必须是整数：{0!r}".format(retries))
            if config.retries < 0:
                raise MeoWConfigError("retries 不能为负数：{0!r}".format(retries))
        default_title = data.get("default_title")
        if default_title:
            config.default_title = str(default_title)
        default_category = data.get("default_category")
        if default_category:
            config.default_category = str(default_category)
        return config

    def apply_env(self, environ: Optional[Mapping[str, str]] = None) -> "Config":
        """Apply ``MEOW_*`` overrides on top of the file contents.

        These are meant for one-off runs and CI; they are never persisted.
        """
        env = os.environ if environ is None else environ
        if env.get("MEOW_NICKNAME"):
            self.nickname = env["MEOW_NICKNAME"].strip()
        if env.get("MEOW_BASE_URL"):
            self.base_url = _clean_base_url(env["MEOW_BASE_URL"], self.path)
        if env.get("MEOW_TIMEOUT"):
            try:
                self.timeout = float(env["MEOW_TIMEOUT"])
            except ValueError:
                raise MeoWConfigError(
                    "MEOW_TIMEOUT 必须是数字：{0!r}".format(env["MEOW_TIMEOUT"])
                )
        return self

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nickname": self.nickname,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "retries": self.retries,
            "default_title": self.default_title,
            "default_category": self.default_category,
        }

    def save(self, path: Optional[Any] = None) -> Path:
        """Atomically write the config, with ``0600`` permissions on POSIX."""
        target = Path(path).expanduser() if path else (self.path or default_config_path())
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.to_dict(), ensure_ascii=False, indent=2) + "\n"
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        if os.name != "nt":
            try:
                os.chmod(tmp, 0o600)
            except OSError:
                pass
        os.replace(tmp, target)
        self.path = target
        return target

    # -- nickname ---------------------------------------------------------
    def ensure_nickname(
        self,
        *,
        prompt: bool = True,
        input_fn: Callable[[str], str] = input,
        print_fn: Callable[[str], None] = print,
        save: bool = True,
    ) -> str:
        """Return a usable nickname, asking the user once if allowed to.

        ``prompt=False`` is the right choice for library callers: a missing
        nickname must surface as a clear error, never as a blocked process.
        """
        if self.nickname:
            return validate_nickname(self.nickname)
        if not prompt:
            raise MeoWConfigError(
                "尚未配置 MeoW 昵称。请先运行：meowpush config set <你的昵称>\n"
                "（昵称即专属推送链接 {0}/<昵称>/ 中的那一段；"
                "也可用 --nickname 临时指定，或设置 MEOW_NICKNAME）".format(
                    self.base_url.rstrip("/")
                )
            )
        nickname = prompt_for_nickname(input_fn=input_fn, print_fn=print_fn)
        self.nickname = nickname
        if save:
            saved = self.save()
            print_fn("已保存配置：{0}".format(saved))
        return nickname


def prompt_for_nickname(
    input_fn: Callable[[str], str] = input,
    print_fn: Callable[[str], None] = print,
    attempts: int = 3,
) -> str:
    """Ask the user for a nickname, retrying on invalid input."""
    print_fn("首次使用需要设置 MeoW 昵称（昵称即专属推送链接中的那一段）。")
    for remaining in range(attempts, 0, -1):
        try:
            raw = input_fn("请输入 MeoW 昵称: ")
        except EOFError:
            raise MeoWConfigError("未读取到昵称输入（stdin 已关闭），已取消。")
        try:
            return validate_nickname(raw)
        except MeoWError as exc:
            print_fn("昵称无效：{0}".format(exc))
            if remaining <= 1:
                break
    raise MeoWConfigError("未获得有效的 MeoW 昵称，已取消。")


def _clean_base_url(value: str, path: Optional[Path]) -> str:
    url = value.strip().rstrip("/")
    lowered = url.lower()
    if not (lowered.startswith("http://") or lowered.startswith("https://")):
        raise MeoWConfigError(
            "base_url 必须以 http:// 或 https:// 开头：{0!r}{1}".format(
                value, "（{0}）".format(path) if path else ""
            )
        )
    return url
