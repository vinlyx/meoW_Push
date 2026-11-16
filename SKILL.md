---
name: meow-push
description: 通过 MeoW 把通知推送到鸿蒙（HarmonyOS）手机，基于 https://api.chuckfang.com 的 HTTP 接口，默认 POST + JSON。支持标题、跳转链接、图标、自定义分类、HTML 正文，内置本地频率限制与错误码映射。触发场景：用户说「发个推送」「推送到我手机」「通知我」「MeoW 推送」「任务跑完提醒我」「告警推手机」等。
agent_created: true
---

# MeoW 手机通知推送

把一段文本（或 HTML）推到用户鸿蒙手机上的 MeoW App。仓库同时是 Python 库，其他项目可直接 `from meow_push import send`。

## 何时使用

- 用户要求「跑完/失败/告警时通知我」「推送到手机」「发个 MeoW」
- 长任务收尾时主动补一条结果通知（用户明确要过才发，别自作主张刷屏）

## 第 0 步：确认昵称

昵称只在**首次使用**时向用户询问一次，保存进 config，之后不再问。**不要**把昵称写进代码或仓库里的任何文件。

> 下文统一写 `meowpush`；未安装时替换成 `<仓库根目录>/bin/meowpush`。

```bash
meowpush config show        # nickname 为空 → 未配置
```

- 已配置：直接进入发送。
- 未配置：向用户确认昵称，然后写入：

```bash
meowpush config set <昵称>
```

告诉用户：昵称就是专属推送链接 `https://api.chuckfang.com/<昵称>/` 里的那一段，不能含斜杠。配置落在 `~/.config/meow-push/config.json`（Windows 为 `%APPDATA%\meow-push\config.json`），在仓库之外，不会被提交。

> 交互式终端下直接 `python3 -m meow_push send "hi"` 也会提示输入昵称并自动保存；在 Agent 的非交互环境里必须先用 `config set`，否则会报错退出（退出码 5）。

## 发送

三种等价入口，按可用性择一：

1. `meowpush` —— 已 `pip install -e .` 时，任意目录可用
2. `<仓库根目录>/bin/meowpush` —— 未安装时，任意目录可用（脚本会自行处理 `PYTHONPATH`）
3. `python3 -m meow_push` —— 需先 `cd` 到仓库根目录

```bash
meowpush send "构建完成，用时 3m12s" -t CI -c 告警
meowpush send "发布成功" -u https://example.com/release/1
meowpush send "<b>完成</b>，耗时 3m12s" --html --html-height 300
echo "最后 20 行日志" | meowpush send --stdin -t 服务器
meowpush send "hi" --dry-run     # 只打印请求，不发送
meowpush send "hi" --json        # 机器可读输出
```

| 参数 | 说明 |
| --- | --- |
| `msg` / `--stdin` / `-` | 消息内容（必填），`-` 表示从标准输入读 |
| `-t/--title` | 标题，缺省服务端填 `MeoW` |
| `-u/--url` | 点击跳转链接，必须 http/https |
| `-i/--img-url` | 图标 URL，建议 216×216 PNG |
| `-c/--category` | 分类，**≤10 个字**，不能含换行 |
| `--html` | 按 HTML 渲染（`msgType=html`） |
| `--html-height` | HTML 显示高度 px，仅 `--html` 时有效；缺省随字号自适应 |
| `--font-size` | HTML 基础字号 px，默认 48（App 原始渲染约 10px） |
| `--width` | HTML 内容宽度 px，默认 900（约 18 汉字/行，防横向溢出） |
| `--css` | 追加自定义 CSS，`@file.css` 从文件读；排在默认样式之后 |
| `--no-html-wrap` | 关闭默认样式包装，原样发送片段 |
| `--wait` | 命中本地限流时等待而非报错 |
| `--dry-run` | 不发送，只回显请求 |
| `--json` | 结果以 JSON 输出 |

**HTML 默认样式**：`--html` 时自动包一层 48px 字号、900px 宽、行高 1.55 的容器，并附带标题/列表/代码/表格的基础样式；样式表排在正文之后（避免通知预览被清洗成空白）。因此直接用 `<b>`、`<p>`、`<ul>` 这类简单标签即可，**不要**再手写小字号 `font-size`。需要微调时用 `--font-size` / `--width` / `--css`；发完整 HTML 文档时不会被二次包装。

## 失败排查

HTTP 状态**恒为 200**，要看响应 JSON 的 `status`（CLI 已映射为退出码）：

| status / 退出码 | 含义 | 处理 |
| --- | --- | --- |
| 200 / 0 | 成功 | — |
| 400 / 4 | 参数错误 | 检查分类是否超 10 字、含换行，或标题/内容为空 |
| 403 / 4 | 内容策略禁止 | 换措辞，别发被拦截的内容 |
| 404 / 4 | 昵称未注册 | 核对 `config show` 里的 nickname |
| 429 / 6 | 频率超限 | 等 3 秒以上；批量场景加 `--wait` |
| 500 / 4 | 服务端错误 | 客户端已自动重试 2 次，仍失败则稍后再试 |
| — / 3 | 网络不通/超时 | 检查网络或代理；`--timeout` 调大 |
| — / 5 | 未配置昵称/配置损坏 | `config set <昵称>` |

## 作为库调用

```python
from meow_push import send, MeoWClient, MeoWAPIError

send("构建完成", title="CI", category="告警")

client = MeoWClient("your-nickname", timeout=5, retries=3)   # 不依赖配置文件
client.send("<b>完成</b>", msg_type="html", html_height=280)
```

库调用**不会**交互提示昵称：缺配置时抛 `MeoWConfigError`，需要显式传 `nickname=` 或先写好 config。

## 约束

- 昵称=推送凭证，等同于密码：不写进代码、不提交、不贴公开日志。
- 本地限流**默认关闭**（会员账号无服务端配额）；非会员或怀疑被限流时加 `--rate-limit`，或配置 `rate_limit: true`。
- 服务端对非会员的配额：3 秒 1 条、每分钟 15 条、每小时 60 条、每天 1000 条；不要用公共出口 IP 批量推送。
- 只发用户真正需要看到的通知；成功/失败各一条，别对中间步骤逐条推送。
