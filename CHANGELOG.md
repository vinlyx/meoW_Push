# Changelog

## v1.0.0 — 2026-11-16

首个稳定版本：把通知推送到鸿蒙（HarmonyOS）手机上的 MeoW App，零第三方依赖。

### 功能

- **推送**：`send` 走 POST + JSON，支持标题、跳转链接、图标与自定义分类（≤10 字）。
- **HTML**：`--html` 自动套默认样式（48px 字号 / 900px 宽 / 行高 1.55），高度按约 5 行自适应；样式表排在正文之后，避免折叠通知预览被清洗成空白。
- **可覆盖**：`--font-size`、`--width`、`--css`（支持 `@file.css`）、`--no-html-wrap`，以及配置项 `html_font_size` / `html_width` / `html_css` / `html_wrap`。
- **配置**：昵称首次使用时询问并写入用户目录（POSIX `0600`，Windows `%APPDATA%`），不落仓库；支持 `--config`、`MEOW_CONFIG` 与 `MEOW_*` 环境变量。
- **入口**：`meowpush`（pip 安装）、`bin/meowpush`（免安装、任意目录）、`python3 -m meow_push`（仓库根）。
- **错误模型**：业务 `status` 映射为异常与稳定退出码（0/2/3/4/5/6），`--json` 便于脚本与 Agent 解析。
- **频率限制**：默认关闭（会员无配额），`--rate-limit` 或配置 `rate_limit: true` 可开启本地 3s/15min/60h 保护。
- **兼容性**：Python ≥ 3.8，WSL / Linux / macOS / Windows 通用，仅用标准库。

### 验证

- 67 项单元测试，WSL Python 3.10 与 Windows Python 3.13 均通过；CI 覆盖 3.8 / 3.10 / 3.12 / 3.13。
