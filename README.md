# rednote-crawler

[中文](#中文) | [English](#english)

---

## 中文

小红书 (Xiaohongshu / REDnote) 数据采集框架 + MCP 服务。

基于 Playwright 实现真实浏览器自动化，具备双层反检测能力（playwright-stealth + browserforge）。通过 MCP 协议将采集能力暴露为标准工具，让 AI 助手（Claude Desktop / Code / Cursor）直接调用。

### 功能特性

- **MCP 服务**：AI 助手可直接搜索小红书、采集笔记详情和评论
- **多种 Transport**：stdio（本地）/ SSE（远程部署）/ Streamable HTTP
- 关键词搜索采集（瀑布流自动滚动加载）
- 笔记详情采集（标题、正文、互动数据、标签、图片/视频）
- 评论采集（Top N 评论，含用户信息和 IP 属地）
- 双层反检测（playwright-stealth 环境级 + browserforge 指纹级）
- 登录状态持久化（扫码登录后自动保存，下次启动免登录）
- 数据输出：JSON（原始完整）+ Excel/xlsx（3 个 Sheet 结构化）
- 生产级稳定性：超时控制、浏览器崩溃自动恢复、登录态失效检测

### 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url> && cd rednote-crawler

# 2. 安装依赖
uv sync

# 3. 安装浏览器
uv run playwright install chromium

# 4. 首次登录（扫码）
uv run python scripts/verify_login.py

# 5. 运行采集
uv run python main.py
```

### MCP 服务使用

#### 方式一：stdio 模式（推荐，本地集成）

在 Claude Desktop 配置文件中添加（Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`）：

```json
{
  "mcpServers": {
    "rednote-crawler": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rednote-crawler", "python", "mcp_server.py"],
      "env": {}
    }
  }
}
```

#### 方式二：SSE 模式（远程部署）

```bash
# 服务器端启动
uv run python mcp_server.py --transport sse --host 0.0.0.0 --port 8000
```

客户端配置：

```json
{
  "mcpServers": {
    "rednote-crawler": {
      "url": "http://your-server:8000/sse"
    }
  }
}
```

#### 方式三：Streamable HTTP 模式

```bash
uv run python mcp_server.py --transport streamable-http --host 0.0.0.0 --port 8000
```

### MCP 工具列表

| 工具 | 说明 | 耗时 |
|------|------|------|
| `check_login_status` | 检查登录状态 | 5-10s |
| `search_notes` | 关键词搜索笔记（max_count 1-50） | 30-90s |
| `get_note_detail` | 采集笔记详情 + 评论 | 15-60s |
| `crawl_keyword` | 完整流程：搜索→详情→评论→存储 | 2-15min |
| `get_saved_data` | 查询本地已保存数据 | <1s |

### 命令参考

| 命令 | 说明 |
|------|------|
| `uv sync` | 安装/同步项目依赖 |
| `uv run playwright install chromium` | 安装 Chromium 浏览器 |
| `uv run python main.py` | 运行完整采集流程 |
| `uv run python mcp_server.py` | 启动 MCP 服务（stdio） |
| `uv run python mcp_server.py --transport sse` | 启动 MCP 服务（SSE） |
| `uv run python scripts/verify_login.py` | 验证/完成登录 |
| `uv run python scripts/verify_stealth.py` | 验证反检测效果 |
| `uv run python scripts/verify_search.py` | 验证搜索采集 |
| `uv run python scripts/verify_note.py` | 验证笔记详情+评论采集 |
| `uv run pytest --cov` | 运行测试 + 覆盖率 |

### 配置说明

编辑 `config/settings.yaml`：

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `crawler.keywords` | `["示例关键词"]` | 搜索关键词列表 |
| `crawler.max_notes_per_keyword` | `20` | 每个关键词最多采集笔记数 |
| `crawler.max_comments_per_note` | `20` | 每条笔记最多采集评论数 |
| `crawler.scroll_pause` | `1.5` | 滚动后等待时间（秒） |
| `crawler.page_load_timeout` | `30` | 页面加载超时（秒） |
| `delay.between_notes` | `[2, 5]` | 笔记之间随机延迟范围（秒） |
| `delay.between_searches` | `[3, 8]` | 搜索之间随机延迟范围（秒） |
| `browser.headless` | `false` | 是否无头模式 |
| `storage.output_dir` | `"data"` | 输出目录 |
| `storage.save_raw_json` | `true` | 是否保存原始 JSON |
| `storage.save_xlsx` | `true` | 是否保存 Excel |

### 输出格式

```
data/
├── raw/
│   ├── {keyword}_{timestamp}.json          # 搜索结果
│   └── notes_{keyword}_{timestamp}.json    # 笔记详情+评论
└── processed/
    └── {keyword}_{timestamp}.xlsx          # Excel 工作簿
        ├── Sheet 1: 搜索结果 (8 列)
        ├── Sheet 2: 笔记详情 (13 列)
        └── Sheet 3: 评论数据 (8 列)
```

### 项目结构

```
mcp_server.py          # MCP 服务入口（支持 stdio / SSE / HTTP）
main.py                # CLI 采集入口
src/
├── session.py         # MCP 会话管理（浏览器生命周期 + 并发锁）
├── errors.py          # 统一错误格式
├── stealth.py         # 反检测配置（指纹生成 + stealth 注入）
├── browser.py         # Playwright 浏览器生命周期管理
├── auth.py            # 登录 & 会话管理
├── search.py          # 搜索结果采集（瀑布流滚动）
├── note.py            # 笔记详情采集（含重试逻辑）
├── comment.py         # 评论采集（Top N）
├── parser.py          # 页面数据解析
└── storage.py         # 数据存储（JSON + Excel/xlsx）
scripts/               # 验证脚本
config/                # YAML 配置
tests/                 # 测试套件
```

### 依赖

| 包 | 用途 |
|----|------|
| playwright | 浏览器自动化 (async API) |
| playwright-stealth | 反检测补丁 |
| browserforge | 真实浏览器指纹生成 |
| mcp[cli] | MCP 协议 SDK |
| uvicorn | ASGI 服务器（SSE/HTTP transport） |
| starlette | ASGI 框架（SSE/HTTP transport） |
| pyyaml | YAML 配置加载 |
| openpyxl | Excel 工作簿生成 |

### 许可证

MIT

---

## English

Xiaohongshu (REDnote) data collection framework + MCP server.

Built on Playwright for real browser automation with dual-layer anti-detection (playwright-stealth + browserforge). Exposes collection capabilities as standard MCP tools for AI assistants (Claude Desktop / Code / Cursor).

### Features

- **MCP Server**: AI assistants can directly search REDnote, collect note details and comments
- **Multiple Transports**: stdio (local) / SSE (remote) / Streamable HTTP
- Keyword search with infinite scroll auto-loading
- Note detail collection (title, content, engagement metrics, tags, images/videos)
- Comment collection (Top N comments with user info and IP location)
- Dual-layer anti-detection (environment-level + fingerprint-level)
- Persistent login state (auto-saved after QR code scan)
- Output: JSON (raw) + Excel/xlsx (3-sheet structured)
- Production-grade reliability: timeout control, browser crash auto-recovery, login expiry detection

### Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) package manager

### Quick Start

```bash
# 1. Clone
git clone <repo-url> && cd rednote-crawler

# 2. Install dependencies
uv sync

# 3. Install browser
uv run playwright install chromium

# 4. First login (QR code scan)
uv run python scripts/verify_login.py

# 5. Run collection
uv run python main.py
```

### MCP Server Usage

#### Option A: stdio Mode (Recommended, Local Integration)

Add to Claude Desktop config (Mac: `~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rednote-crawler": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/rednote-crawler", "python", "mcp_server.py"],
      "env": {}
    }
  }
}
```

#### Option B: SSE Mode (Remote Deployment)

```bash
# Start on server
uv run python mcp_server.py --transport sse --host 0.0.0.0 --port 8000
```

Client config:

```json
{
  "mcpServers": {
    "rednote-crawler": {
      "url": "http://your-server:8000/sse"
    }
  }
}
```

#### Option C: Streamable HTTP Mode

```bash
uv run python mcp_server.py --transport streamable-http --host 0.0.0.0 --port 8000
```

### MCP Tools

| Tool | Description | Latency |
|------|-------------|---------|
| `check_login_status` | Check login status | 5-10s |
| `search_notes` | Search notes by keyword (max_count 1-50) | 30-90s |
| `get_note_detail` | Collect note details + comments | 15-60s |
| `crawl_keyword` | Full pipeline: search → details → comments → save | 2-15min |
| `get_saved_data` | Query locally saved data files | <1s |

### CLI Reference

| Command | Description |
|---------|-------------|
| `uv run python mcp_server.py` | Start MCP server (stdio) |
| `uv run python mcp_server.py --transport sse` | Start MCP server (SSE) |
| `uv run python mcp_server.py --transport sse --host 0.0.0.0 --port 9090` | SSE with custom host/port |
| `uv run python main.py` | Run full collection pipeline |
| `uv run python scripts/verify_login.py` | Login via QR code |
| `uv run pytest --cov` | Run tests with coverage |

### Project Structure

```
mcp_server.py          # MCP server entry (stdio / SSE / HTTP)
main.py                # CLI collection entry
src/
├── session.py         # MCP session (browser lifecycle + concurrency lock)
├── errors.py          # Unified error format
├── stealth.py         # Anti-detection (fingerprint + stealth injection)
├── browser.py         # Playwright browser lifecycle
├── auth.py            # Login & session management
├── search.py          # Search collection (infinite scroll)
├── note.py            # Note detail collection (with retry)
├── comment.py         # Comment collection (Top N)
├── parser.py          # Page data parsing
└── storage.py         # Data storage (JSON + Excel/xlsx)
```

### License

MIT
