# meow-push

[![CI](https://github.com/vinlyx/meoW_Push/actions/workflows/ci.yml/badge.svg)](https://github.com/vinlyx/meoW_Push/actions/workflows/ci.yml)

把通知推送到鸿蒙（HarmonyOS）手机上的 MeoW App，零第三方依赖，WSL / Linux / macOS / Windows 通用。

- 服务端接口：<https://www.chuckfang.com/MeoW/api_doc.html>
- 默认走 **POST + JSON**（长文本、HTML 正文不进 URL）
- 既是 **WorkBuddy Skill**（见 `SKILL.md`），也是可被任意 Python 项目导入的库

## 安装

```bash
# 方式一：可编辑安装（推荐，获得 meowpush 命令）
pip install -e .

# 方式二：不安装，用自带启动脚本（任意目录可用）
/path/to/meowMsg/bin/meowpush send "hello"

# 方式三：不安装，在仓库根目录用模块方式运行
python3 -m meow_push send "hello"

# 方式四：把 meow_push/ 目录整个拷进你的项目，直接 import
```

要求 Python ≥ 3.12（CI 覆盖 3.12 / 3.13 / 3.14），仅使用标准库（`urllib` / `json` / `argparse`）。

## 作为 WorkBuddy Skill 使用

仓库自带 `SKILL.md`，放进 WorkBuddy 的 skills 目录即可被「发个推送」「通知我」这类说法命中。目录名建议用 `meow-push`，与 `SKILL.md` 的 `name` 保持一致：

```bash
# Linux / WSL / macOS
ln -s "$PWD" ~/.workbuddy/skills/meow-push

# Windows（管理员 PowerShell）
# New-Item -ItemType SymbolicLink -Path "$env:USERPROFILE\.workbuddy\skills\meow-push" -Target "D:\path\to\meowMsg"
```

Skill 被调用时会先执行 `config show` 判断昵称是否已配置，未配置则询问用户一次。

## 首次配置

昵称就是专属推送链接 `https://api.chuckfang.com/<昵称>/` 里的那一段，**不能含斜杠**。

```bash
meowpush config set Vinlyx      # 显式写入
meowpush send "hello"           # 未配置时会在终端里询问昵称并保存
meowpush config show            # 查看当前配置与来源路径
```

配置文件默认写到用户目录，**不在仓库内**，因此不会被提交到 GitHub：

| 平台 | 路径 |
| --- | --- |
| Linux / WSL / macOS | `~/.config/meow-push/config.json`（尊重 `XDG_CONFIG_HOME`） |
| Windows | `%APPDATA%\meow-push\config.json` |

POSIX 下权限为 `0600`。也可以用 `--config <path>` 或环境变量 `MEOW_CONFIG` 指向项目内的文件（`.gitignore` 已覆盖 `meow.config.json`、`*.local.json`）。

配置项：

| 键 | 说明 | 默认 |
| --- | --- | --- |
| `nickname` | MeoW 昵称 | 空（必填） |
| `base_url` | API 根地址 | `https://api.chuckfang.com` |
| `timeout` | 请求超时（秒） | `10.0` |
| `retries` | 瞬时错误重试次数 | `2` |
| `default_title` | 未传 `-t` 时的默认标题 | `null` |
| `default_category` | 未传 `-c` 时的默认分类 | `null` |
| `html_font_size` | HTML 基础字号（px，8–200） | `48` |
| `html_width` | HTML 内容宽度（px，200–2400） | `900` |
| `html_css` | 追加到默认样式之后的 CSS | `null` |
| `html_wrap` | 是否启用默认样式包装 | `true` |
| `rate_limit` | 是否启用本地频率限制 | `false` |

环境变量 `MEOW_NICKNAME` / `MEOW_BASE_URL` / `MEOW_TIMEOUT` 可临时覆盖，且不会写回文件。

## 命令行用法

```bash
meowpush send "构建完成" -t CI -c 告警
meowpush send "发布成功" -u https://example.com/release/1 -i https://example.com/icon.png
meowpush send "<b>完成</b>，耗时 3m12s" --html --html-height 300
echo "最后 20 行日志" | meowpush send --stdin -t 服务器
meowpush send "hi" --dry-run          # 只打印请求，不发送
meowpush test                          # 发一条带时间戳的测试通知
meowpush "省略 send 也行"               # 便捷写法
```

参数（对应官方接口）：

| 参数 | 位置 | 说明 |
| --- | --- | --- |
| `msg` / `--stdin` | JSON body | 必填，消息内容 |
| `-t/--title` | JSON body | 通知标题，缺省由服务端填 `MeoW` |
| `-u/--url` | JSON body | 点击通知的跳转链接（http/https） |
| `-i/--img-url` | JSON body | 通知图标，建议 216×216 PNG |
| `-c/--category` | JSON body | 自定义分类，**最多 10 个字**，不能含换行 |
| `--html` | query | `msgType=html`，在 App 内渲染 HTML |
| `--html-height` | query | HTML 显示高度（px），仅 `--html` 时有效；缺省随字号自适应 |
| `--font-size` | 包装层 | HTML 基础字号，默认 48px |
| `--width` | 包装层 | HTML 内容宽度，默认 900px |
| `--css` | 包装层 | 追加自定义 CSS，支持 `@file.css` |
| `--no-html-wrap` | 包装层 | 关闭默认样式，原样发送片段 |

本地频率限制**默认关闭**（会员账号无配额限制）；需要时用 `--rate-limit` 打开，或用配置 `rate_limit: true` 固化。开启后规则为 3 秒 1 条 / 每分钟 15 条 / 每小时 60 条，命中时默认快速报错、`--wait` 改为短暂等待。

## HTML 通知的默认样式

MeoW 的 HTML 视图基础字号很小（约 10px），直接发裸片段在手机上几乎读不清。因此 `--html` 时会自动套一层默认样式：

1. 容器 `<div class="meow-html-push" style="font-size:48px;width:900px;max-width:100%;...">`——**内联样式**，即使 App 过滤掉 `<style>` 标签也能生效，并通过 CSS 继承作用到 `p` / `li` / `span` 等子元素；
2. 一段类作用域样式表，补齐标题层级（h1–h6）、列表缩进、图片自适应、行内代码换行、表格边框。**它排在正文之后**：MeoW 用消息开头若干字符生成折叠通知的预览，样式表放在最前面会被清洗成空白正文。

两个尺寸是按实测定的，不是拍脑袋：

- **字号 48px**：48px 是鸿蒙端可读且不浪费空间的档位（约为裸片段的 4.8 倍）；
- **宽度 900px**：48px 下约 24 个混合字符（约 1000px）就贴到卡片右边缘，因此把容器固定为 900px，约 18 个汉字/行换行，`max-width:100%` 保证窄屏不溢出。

设计上的克制：

- **不设置文字颜色和背景色**，让 App 的浅色/深色主题各自生效；
- 不引入外部字体、脚本或远程资源，离线也能正常渲染；
- 只作用于 `.meow-html-push` 内部，不会污染宿主界面。

`htmlHeight` 缺省随字号自适应（约 5 行：48px → 370px），显式传 `--html-height` 优先。

覆盖方式，从轻到重：

```bash
meowpush send "..." --html --font-size 40              # 只改字号
meowpush send "..." --html --width 700                 # 只改每行宽度
meowpush send "..." --html --css "@my.css"             # 追加样式表文件
meowpush send "..." --html --css ".meow-html-push p{margin:0}"   # 内联一段
meowpush send "..." --html --no-html-wrap              # 完全关闭包装
```

`--css` 的内容排在默认样式**之后**，同优先级下后写的规则生效；需要压过继承时把选择器写具体一点（如 `.meow-html-push p`）。若内容本身已是完整的 `<html>` 文档，则原样发送，不再包装。

想长期固定，写进配置即可：

```bash
meowpush config set Vinlyx    # 保留昵称
# 再编辑 ~/.config/meow-push/config.json： "html_font_size": 40, "html_width": 820
```

## Python 库用法

```python
from meow_push import MeoWClient, MeoWAPIError, send

# 一行版：读配置，自动复用客户端（含本地限流状态）
send("构建完成", title="CI", category="告警")
send("<b>完成</b>", msg_type="html", html_height=280, url="https://example.com")

# 显式客户端：适合长期运行的服务 / 不依赖配置文件
client = MeoWClient("Vinlyx", timeout=5, retries=3)
result = client.send("磁盘使用率 91%", title="监控", category="告警")
print(result.status, result.message, result.elapsed_ms)

# CI 里捕获错误而不是崩溃
try:
    client.send("部署完成")
except MeoWAPIError as exc:
    print(exc.status, exc.reason, exc.hint)
```

`SendResult` 字段：`ok` / `status` / `message` / `data` / `nickname` / `elapsed_ms`。

## 错误码

HTTP 状态恒为 200，真正的结果在响应 JSON 的 `status` 里，CLI 会映射成退出码：

| 业务 status | 含义 | 退出码 |
| --- | --- | --- |
| 200 | 成功 | 0 |
| 400 | 标题 / 消息 / 分类参数错误 | 4 |
| 403 | 内容策略禁止发送 | 4 |
| 404 | 昵称未注册 | 4 |
| 429 | 服务端频率超限 | 6 |
| 500 | 服务端错误 | 4 |
| — | 网络不可达 / 超时 | 3 |
| — | 参数校验失败 | 2 |
| — | 未配置昵称 / 配置损坏 | 5 |

`--json` 会把结果或错误输出成 JSON，便于脚本和 Agent 解析。

## 开发

```bash
python3 -m unittest discover -s tests -t . -v
```

测试用本地 `http.server` 冒充 MeoW 接口，全程不产生真实推送。

发布：更新 `meow_push/version.py` 与 `pyproject.toml` 的版本号、补 `CHANGELOG.md`，然后打 tag 推送即可——`.github/workflows/release.yml` 会跑测试、构建 sdist/wheel 并创建 GitHub Release。

```bash
git tag v1.0.0 && git push origin v1.0.0
```

## 安全与限制

- 昵称等价于推送凭证：知道昵称的人就能给你发通知，别提交到仓库、别贴进公开日志。
- 不要在多人的公共出口 IP 上批量推送，容易被判定为攻击；可信 IP 可向作者申请白名单。
- 服务端配额：非会员 3 秒 1 条、每分钟 15 条、每小时 60 条、每天 1000 条。

## License

MIT
