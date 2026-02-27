# rednote-crawler

小红书 (Xiaohongshu) 数据采集框架，基于 Playwright 实现真实浏览器自动化，具备双层反检测能力。

## 功能特性

- 关键词搜索采集（瀑布流自动滚动加载）
- 笔记详情采集（标题、正文、互动数据、标签、图片/视频）
- 评论采集（Top N 评论，含用户信息和 IP 属地）
- 双层反检测（playwright-stealth 环境级 + browserforge 指纹级）
- 登录状态持久化（扫码登录后自动保存，下次启动免登录）
- 数据输出：JSON（原始完整）+ Excel/xlsx（3 个 Sheet 结构化）

## 环境要求

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

## 快速开始

```bash
# 1. 克隆仓库
git clone <repo-url> && cd rednote-crawler

# 2. 安装依赖
uv sync

# 3. 安装浏览器
uv run playwright install chromium

# 4. 配置关键词
#    编辑 config/settings.yaml，修改 keywords 列表

# 5. 运行采集
uv run python main.py
```

首次运行会弹出浏览器窗口，需手动扫码登录。登录状态会自动保存，后续运行无需重复登录。

<!-- AUTO-GENERATED: commands-reference -->
## 命令参考

| 命令 | 说明 |
|------|------|
| `uv sync` | 安装/同步项目依赖 |
| `uv run playwright install chromium` | 安装 Chromium 浏览器 |
| `uv run python main.py` | 运行完整采集流程 |
| `uv run python scripts/verify_stealth.py` | 验证反检测效果 |
| `uv run python scripts/verify_login.py` | 验证登录状态 |
| `uv run python scripts/verify_search.py` | 验证搜索采集 |
| `uv run python scripts/verify_note.py` | 验证笔记详情+评论采集 |
| `uv run python scripts/verify_e2e.py` | 端到端集成验证 |
| `uv add <package>` | 添加新依赖 |
<!-- /AUTO-GENERATED: commands-reference -->

## 配置说明

编辑 `config/settings.yaml`：

<!-- AUTO-GENERATED: config-reference -->
| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `crawler.keywords` | `["示例关键词"]` | 搜索关键词列表 |
| `crawler.max_notes_per_keyword` | `20` | 每个关键词最多采集笔记数 |
| `crawler.max_comments_per_note` | `20` | 每条笔记最多采集评论数 |
| `crawler.scroll_pause` | `1.5` | 滚动后等待时间（秒） |
| `crawler.page_load_timeout` | `30` | 页面加载超时（秒） |
| `delay.between_notes` | `[2, 5]` | 笔记之间随机延迟范围（秒） |
| `delay.between_searches` | `[3, 8]` | 搜索之间随机延迟范围（秒） |
| `delay.scroll_interval` | `[1, 3]` | 滚动间隔随机延迟范围（秒） |
| `browser.headless` | `false` | 是否无头模式 |
| `storage.output_dir` | `"data"` | 输出目录 |
| `storage.save_raw_json` | `true` | 是否保存原始 JSON |
| `storage.save_xlsx` | `true` | 是否保存 Excel |
<!-- /AUTO-GENERATED: config-reference -->

## 输出格式

采集数据保存在 `data/` 目录：

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

## 项目结构

```
src/
├── stealth.py     # 反检测配置（指纹生成 + stealth 注入）
├── browser.py     # Playwright 浏览器生命周期管理
├── auth.py        # 登录 & 会话管理
├── search.py      # 搜索结果采集（瀑布流滚动）
├── note.py        # 笔记详情采集（含重试逻辑）
├── comment.py     # 评论采集（Top N）
├── parser.py      # 页面数据解析（搜索卡片 / 详情 / 评论）
└── storage.py     # 数据存储（JSON + Excel/xlsx）
scripts/           # 验证脚本
config/            # YAML 配置
main.py            # 入口文件
```

<!-- AUTO-GENERATED: dependencies -->
## 依赖

| 包 | 版本 | 用途 |
|----|------|------|
| playwright | >=1.58.0 | 浏览器自动化 (async API) |
| playwright-stealth | >=2.0.2 | 反检测补丁 |
| browserforge | >=1.2.4 | 真实浏览器指纹生成 |
| pyyaml | >=6.0.3 | YAML 配置加载 |
| openpyxl | >=3.1.5 | Excel 工作簿生成 |
<!-- /AUTO-GENERATED: dependencies -->

## 许可证

MIT
