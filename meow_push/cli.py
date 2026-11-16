"""Command line interface.

Installed as ``meowpush``; also runnable via ``python3 -m meow_push``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

from .client import MeoWClient, SendResult
from .config import Config, default_config_path, prompt_for_nickname
from .errors import MeoWError, MeoWValidationError
from .validators import validate_message, validate_nickname
from .version import __version__

COMMANDS = ("send", "test", "config")

#: Global options that consume the next argv entry.
_VALUE_OPTIONS = {"--config", "--nickname", "--base-url", "--timeout", "--retries"}


def build_parser() -> argparse.ArgumentParser:
    # ``default=SUPPRESS`` is essential: with argparse sub-parsers, a parent
    # parser default would otherwise overwrite values already parsed before the
    # sub-command (e.g. ``meowpush --config X send hi``).
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", metavar="PATH", default=argparse.SUPPRESS,
                        help="配置文件路径（默认 ~/.config/meow-push/config.json）")
    common.add_argument("--nickname", metavar="NAME", default=argparse.SUPPRESS,
                        help="临时覆盖昵称，不写入配置")
    common.add_argument("--base-url", metavar="URL", default=argparse.SUPPRESS,
                        help="覆盖 API 根地址（默认 https://api.chuckfang.com）")
    common.add_argument("--timeout", type=float, metavar="SEC", default=argparse.SUPPRESS,
                        help="请求超时秒数")
    common.add_argument("--retries", type=int, metavar="N", default=argparse.SUPPRESS,
                        help="瞬时错误重试次数")
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="以 JSON 输出结果（便于脚本/Agent 解析）")
    common.add_argument("-v", "--verbose", action="store_true", default=argparse.SUPPRESS,
                        help="输出更多细节")

    parser = argparse.ArgumentParser(
        prog="meowpush",
        description="通过 MeoW 向鸿蒙手机推送通知（默认 POST + JSON）",
        parents=[common],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  meowpush send \"构建完成\" -t CI -c 告警\n"
            "  meowpush send \"<b>完成</b>\" --html --html-height 300 -u https://example.com\n"
            "  echo \"日志尾部\" | meowpush send --stdin -t 服务器\n"
            "  meowpush config set Vinlyx\n"
            "  meowpush test\n"
        ),
    )
    parser.add_argument("--version", action="version", version="meow-push {0}".format(__version__))
    sub = parser.add_subparsers(dest="command")

    send_parser = sub.add_parser("send", parents=[common], help="发送一条通知")
    send_parser.add_argument("msg", nargs="?", help="消息内容；用 - 表示从 stdin 读取")
    send_parser.add_argument("-t", "--title", help="通知标题（默认 MeoW）")
    send_parser.add_argument("-u", "--url", help="点击通知跳转的链接")
    send_parser.add_argument("-i", "--img-url", dest="img_url", help="通知图标 URL（建议 216x216 PNG）")
    send_parser.add_argument("-c", "--category", help="自定义分类（最多 10 个字）")
    send_parser.add_argument("--html", action="store_true", help="按 HTML 渲染消息（msgType=html）")
    send_parser.add_argument("--html-height", dest="html_height", type=int,
                             help="HTML 显示高度（像素，仅 --html 时生效；默认随字号自适应）")
    send_parser.add_argument("--font-size", dest="html_font_size", type=int, metavar="PX",
                             help="HTML 基础字号，默认 40px（可用配置 html_font_size 覆盖）")
    send_parser.add_argument("--css", dest="html_css", metavar="CSS",
                             help="追加自定义 CSS，可写 @file.css 从文件读取；排在默认样式之后")
    send_parser.add_argument("--no-html-wrap", dest="no_html_wrap", action="store_true",
                             help="关闭默认样式包装，原样发送 HTML 片段")
    send_parser.add_argument("--stdin", action="store_true", help="从 stdin 读取消息内容")
    send_parser.add_argument("--dry-run", dest="dry_run", action="store_true",
                             help="只打印请求，不真正发送")
    send_parser.add_argument("--wait", action="store_true",
                             help="命中本地频率限制时短暂等待，而不是直接报错")
    send_parser.add_argument("--no-rate-limit", dest="no_rate_limit", action="store_true",
                             help="关闭本地频率限制（服务端限制仍然生效）")
    send_parser.add_argument("--no-prompt", dest="no_prompt", action="store_true",
                             help="缺少昵称时不交互询问，直接报错")

    test_parser = sub.add_parser("test", parents=[common], help="发送一条测试通知")
    test_parser.add_argument("--no-prompt", dest="no_prompt", action="store_true",
                             help="缺少昵称时不交互询问，直接报错")

    config_parser = sub.add_parser("config", parents=[common], help="查看或修改配置")
    config_sub = config_parser.add_subparsers(dest="config_command")
    config_sub.add_parser("show", parents=[common], help="显示当前配置（JSON）")
    config_sub.add_parser("path", parents=[common], help="显示配置文件路径")
    init_parser = config_sub.add_parser("init", parents=[common], help="初始化配置（会询问昵称）")
    init_parser.add_argument("--force", action="store_true", help="即使已有昵称也重新写入")
    set_parser = config_sub.add_parser("set", parents=[common], help="设置昵称")
    set_parser.add_argument("nickname_value", nargs="?", metavar="NICKNAME",
                            help="要保存的昵称（省略则交互询问）")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    _configure_stdio()
    args = _normalize_argv(list(sys.argv[1:] if argv is None else argv))
    parser = build_parser()
    parsed = parser.parse_args(args)

    try:
        if parsed.command == "config":
            return _run_config(parsed)
        if parsed.command in ("send", "test"):
            return _run_send(parsed)
        parser.print_help()
        return 0
    except MeoWError as exc:
        return _report_error(exc, parsed)


# -- commands -------------------------------------------------------------
def _run_send(args: argparse.Namespace) -> int:
    config = Config.load(_opt(args, "config"))
    _apply_overrides(config, args)

    is_test = args.command == "test"
    if is_test:
        msg = _test_message()
        title = "MeoW 测试"
        category = "测试"
        msg_type = "text"
        html_height = None
        dry_run = False
    else:
        msg = _read_message(args)
        title = _opt(args, "title") or config.default_title
        category = _opt(args, "category")
        if category is None:
            category = config.default_category
        msg_type = "html" if _opt(args, "html", False) else "text"
        html_height = _opt(args, "html_height")
        dry_run = _opt(args, "dry_run", False)

    nickname = config.ensure_nickname(prompt=_can_prompt(args))
    client = MeoWClient(
        nickname,
        base_url=config.base_url,
        timeout=config.timeout,
        retries=config.retries,
        rate_limit=not _opt(args, "no_rate_limit", False),
        wait_on_rate_limit=_opt(args, "wait", False),
        html_font_size=config.html_font_size,
        html_css=config.html_css,
        html_wrap=config.html_wrap,
    )
    result = client.send(
        msg,
        title=title,
        url=_opt(args, "url"),
        img_url=_opt(args, "img_url"),
        category=category,
        msg_type=msg_type,
        html_height=html_height,
        html_font_size=_opt(args, "html_font_size"),
        html_css=_load_css(_opt(args, "html_css")),
        html_wrap=False if _opt(args, "no_html_wrap", False) else None,
        dry_run=dry_run,
    )
    _print_result(result, args, dry_run=dry_run)
    return 0


def _run_config(args: argparse.Namespace) -> int:
    sub = getattr(args, "config_command", None)
    config = Config.load(_opt(args, "config"))

    if sub == "path":
        print(config.path or default_config_path())
        return 0

    if sub == "show":
        payload = config.to_dict()
        payload["config_path"] = str(config.path or default_config_path())
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    if sub == "set":
        nickname = getattr(args, "nickname_value", None) or _opt(args, "nickname")
        if not nickname:
            if not _can_prompt(args):
                raise MeoWValidationError("请提供昵称：meowpush config set <NICKNAME>")
            nickname = prompt_for_nickname()
        config.nickname = validate_nickname(nickname)
        saved = config.save()
        print("已保存配置：{0}".format(saved))
        print("昵称：{0}".format(config.nickname))
        return 0

    # ``config`` with no sub-command behaves like ``config init``.
    if sub in (None, "init"):
        force = getattr(args, "force", False)
        if config.nickname and sub == "init" and not force:
            print("配置已存在：{0}（昵称 {1}）".format(config.path, config.nickname))
            print("如需修改：meowpush config set <NICKNAME>")
            return 0
        nickname = _opt(args, "nickname")
        if not nickname:
            if not _can_prompt(args):
                raise MeoWValidationError("请提供昵称：meowpush config set <NICKNAME>")
            nickname = prompt_for_nickname()
        config.nickname = validate_nickname(nickname)
        saved = config.save()
        print("已保存配置：{0}".format(saved))
        return 0

    raise MeoWValidationError("未知的 config 子命令：{0}".format(sub))


# -- helpers --------------------------------------------------------------
def _normalize_argv(argv: List[str]) -> List[str]:
    """Allow ``meowpush "内容"`` as shorthand for ``meowpush send "内容"``."""
    if not argv:
        return ["--help"]
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--":
            index += 1
            break
        if not token.startswith("-"):
            break
        name = token.split("=", 1)[0]
        index += 1
        if "=" not in token and name in _VALUE_OPTIONS:
            index += 1  # skip the option's value
    if index >= len(argv) or argv[index] in COMMANDS:
        return argv
    return argv[:index] + ["send"] + argv[index:]


def _opt(args: argparse.Namespace, name: str, default: Any = None) -> Any:
    return getattr(args, name, default)


def _apply_overrides(config: Config, args: argparse.Namespace) -> None:
    nickname = _opt(args, "nickname")
    if nickname:
        config.nickname = validate_nickname(nickname)
    base_url = _opt(args, "base_url")
    if base_url:
        config.base_url = base_url.strip().rstrip("/")
    timeout = _opt(args, "timeout")
    if timeout is not None:
        if timeout <= 0:
            raise MeoWValidationError("--timeout 必须大于 0")
        config.timeout = float(timeout)
    retries = _opt(args, "retries")
    if retries is not None:
        if retries < 0:
            raise MeoWValidationError("--retries 不能为负数")
        config.retries = int(retries)


def _load_css(value: Optional[str]) -> Optional[str]:
    """Accept inline CSS or ``@path/to/file.css``."""
    if not value:
        return None
    if value.startswith("@"):
        path = Path(value[1:]).expanduser()
        try:
            return path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MeoWValidationError("无法读取 CSS 文件 {0}：{1}".format(path, exc))
    return value


def _read_message(args: argparse.Namespace) -> str:
    if _opt(args, "stdin", False) or args.msg == "-":
        return validate_message(sys.stdin.read())
    if args.msg is None:
        raise MeoWValidationError(
            '缺少消息内容：meowpush send "内容"（或用 --stdin 从标准输入读取）'
        )
    return validate_message(args.msg)


def _can_prompt(args: argparse.Namespace) -> bool:
    if _opt(args, "no_prompt", False):
        return False
    try:
        return bool(sys.stdin.isatty())
    except (AttributeError, ValueError):
        return False


def _test_message() -> str:
    return "meow-push 测试消息 · {0}".format(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))


def _print_result(result: SendResult, args: argparse.Namespace, *, dry_run: bool = False) -> None:
    if _opt(args, "json", False):
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return
    if dry_run:
        print("dry-run：未发送，请求如下")
        print(json.dumps(result.request, ensure_ascii=False, indent=2))
        return
    print(
        "已发送 → {0} | 状态 {1}（{2}）| {3} ms".format(
            result.nickname, result.status, result.message, result.elapsed_ms
        )
    )


def _report_error(exc: MeoWError, args: argparse.Namespace) -> int:
    exit_code = getattr(exc, "exit_code", 1)
    if _opt(args, "json", False):
        payload = {
            "ok": False,
            "error": type(exc).__name__,
            "message": str(exc),
            "exit_code": exit_code,
        }
        status = getattr(exc, "status", None)
        if status is not None:
            payload["status"] = status
        hint = getattr(exc, "hint", "")
        if hint:
            payload["hint"] = hint
        retry_after = getattr(exc, "retry_after", None)
        if retry_after:
            payload["retry_after"] = round(retry_after, 2)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print("错误：{0}".format(exc), file=sys.stderr)
        hint = getattr(exc, "hint", "")
        if hint:
            print("提示：{0}".format(hint), file=sys.stderr)
        if _opt(args, "verbose", False):
            payload = getattr(exc, "payload", None)
            if payload:
                print("原始响应：{0}".format(json.dumps(payload, ensure_ascii=False)), file=sys.stderr)
    return exit_code


def _configure_stdio() -> None:
    """Force UTF-8 output so Chinese text survives a Windows console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            pass


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
