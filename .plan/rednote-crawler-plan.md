# 小红书数据采集器 — 技术规划

> 基于 Playwright 浏览器自动化，采集搜索结果列表、笔记详情、评论（Top 20）

## 1. 项目概览

### 1.1 目标

用自己的账号登录小红书，通过浏览器自动化方式完成以下数据采集：

| 采集目标 | 说明 |
|----------|------|
| 搜索结果列表 | 按关键词搜索，提取多页笔记摘要信息 |
| 笔记详情 | 进入笔记页，提取完整内容、互动数据 |
| 评论（Top 20） | 提取笔记下前 20 条热门评论 |

### 1.2 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言 | Python 3.10 | 项目已有配置 |
| 包管理 | uv | 项目已有配置 |
| 浏览器自动化 | Playwright | 真实浏览器环境，异步 API |
| 反检测（stealth） | playwright-stealth | 消除 `navigator.webdriver` 等自动化痕迹 |
| 反检测（指纹） | browserforge | 生成真实浏览器指纹（UA、WebGL、Canvas 等） |
| 数据存储 | JSON + CSV | 灵活，方便后续分析 |
| 配置管理 | YAML | 搜索关键词、采集参数外部化 |

### 1.3 反检测方案对比与选型

> **核心问题**：原生 Playwright 虽使用真实 Chromium，但仍暴露多个可被检测的自动化特征。

#### 可被检测的特征

| 特征 | 说明 |
|------|------|
| `navigator.webdriver = true` | Playwright 默认设置，是最基础的检测点 |
| `HeadlessChrome` in UA | 无头模式下 User-Agent 包含标识 |
| WebGL 指纹 | 自动化浏览器的渲染指纹与真实浏览器不同 |
| Canvas 指纹 | 画布渲染结果可被提取用于指纹识别 |
| Chrome DevTools Protocol | CDP 连接本身可被检测 |
| `window.chrome.runtime` | 自动化浏览器缺少此属性 |
| Permissions API | 自动化浏览器的权限查询行为异常 |

#### 方案对比

| 方案 | 反检测能力 | 易用性 | 维护状态 | 适用场景 |
|------|-----------|--------|----------|----------|
| **原生 Playwright** | 低 — 多个特征可被检测 | 高 | 活跃 | 无反爬的站点 |
| **playwright-stealth** | 中 — 覆盖基础检测点 | 高（一行代码接入） | 活跃 | 轻中度反爬 |
| **browserforge** | 中高 — 真实指纹生成 | 高（注入 context） | 活跃 | 指纹检测 |
| **stealth + browserforge** | **高** — 双层防护 | **高** | 活跃 | **推荐组合** |
| **Camoufox** | 很高 — 修改版 Firefox | 中 | 维护停滞 | 高强度反爬 |
| **Crawlee** | 高 — 内置 browserforge | 中（框架较重） | 活跃 | 大规模采集 |

#### 最终选型：`playwright-stealth` + `browserforge`

**理由**：
1. **playwright-stealth** 消除基础自动化痕迹（webdriver 属性、UA 标识、Chrome Runtime 等）
2. **browserforge** 生成与真实浏览器一致的指纹（UA、屏幕分辨率、WebGL、Canvas 等），避免指纹级检测
3. 两者组合使用，侵入性低，无需更换浏览器引擎
4. 对于个人账号、中低频率的采集场景，这套组合足够稳定

---

## 2. 项目结构

```
rednote-crawler/
├── .plan/                      # 规划文档
├── config/
│   └── settings.yaml           # 采集配置（关键词、页数、延迟等）
├── src/
│   ├── __init__.py
│   ├── browser.py              # 浏览器管理（启动、反检测、登录态、持久化）
│   ├── stealth.py              # 反检测配置（stealth + browserforge 集成）
│   ├── auth.py                 # 登录与会话管理
│   ├── search.py               # 搜索结果采集
│   ├── note.py                 # 笔记详情采集
│   ├── comment.py              # 评论采集
│   ├── parser.py               # 页面数据解析（DOM → 结构化数据）
│   └── storage.py              # 数据存储（JSON / CSV）
├── data/                       # 采集数据输出目录
│   ├── raw/                    # 原始 JSON 数据
│   └── processed/              # 处理后的 CSV 数据
├── auth_state/                 # 浏览器登录态存储（.gitignore）
├── main.py                     # 入口
├── pyproject.toml
└── README.md
```

---

## 3. 模块详细设计

### 3.1 反检测配置模块 — `stealth.py`

**职责**：集成 playwright-stealth 和 browserforge，提供反检测能力

**工作原理**：

```
                  ┌──────────────────────────────────┐
                  │         stealth.py                │
                  │                                    │
                  │  ┌──────────────────────────────┐  │
                  │  │   browserforge                │  │
                  │  │   生成真实浏览器指纹            │  │
                  │  │   - User-Agent (匹配 OS/版本)  │  │
                  │  │   - 屏幕分辨率                 │  │
                  │  │   - WebGL 渲染参数             │  │
                  │  │   - Canvas 指纹                │  │
                  │  │   - 语言/时区/平台             │  │
                  │  └──────────────┬───────────────┘  │
                  │                 │                    │
                  │                 ▼                    │
                  │  ┌──────────────────────────────┐  │
                  │  │   playwright-stealth          │  │
                  │  │   消除自动化痕迹               │  │
                  │  │   - 删除 navigator.webdriver   │  │
                  │  │   - 修补 chrome.runtime        │  │
                  │  │   - 伪装 Permissions API       │  │
                  │  │   - 清除 HeadlessChrome UA     │  │
                  │  │   - 修补 iframe contentWindow  │  │
                  │  └──────────────┬───────────────┘  │
                  │                 │                    │
                  │                 ▼                    │
                  │        返回配置好的 context          │
                  └──────────────────────────────────┘
```

**接口设计**：

```python
from browserforge.fingerprints import FingerprintGenerator
from playwright_stealth import stealth_async

class StealthConfig:
    """反检测配置管理"""

    def __init__(self):
        self.fingerprint_generator = FingerprintGenerator(
            browser="chrome",
            os="macos",          # 匹配本机 OS
        )

    def generate_fingerprint(self) -> dict:
        """生成一组真实浏览器指纹"""
        return self.fingerprint_generator.generate()

    async def apply_stealth(self, page: Page) -> None:
        """对页面应用 stealth 补丁"""
        await stealth_async(page)

    def get_context_options(self) -> dict:
        """获取注入指纹后的 browser context 配置"""
        fingerprint = self.generate_fingerprint()
        return {
            "user_agent": fingerprint.navigator.userAgent,
            "viewport": {
                "width": fingerprint.screen.width,
                "height": fingerprint.screen.height,
            },
            "locale": fingerprint.navigator.language,
            "timezone_id": "Asia/Shanghai",
            # browserforge 注入的其他指纹参数
        }
```

**关键点**：
- 每次启动浏览器生成新指纹，避免指纹固化被关联
- fingerprint 的浏览器版本必须与实际 Chromium 版本匹配（否则会被检测到不一致）
- stealth 补丁在每个新页面打开时自动应用

### 3.2 浏览器管理模块 — `browser.py`

**职责**：管理 Playwright 浏览器实例的生命周期，集成反检测

- 启动 Chromium 浏览器（headed / headless 可切换）
- 通过 `StealthConfig` 注入指纹和 stealth 补丁
- 加载已保存的登录态（`storage_state`）
- 提供统一的 `BrowserManager` 上下文管理器

```python
class BrowserManager:
    """
    用法:
        async with BrowserManager(headless=False) as bm:
            page = await bm.new_page()
            ...
    """
    def __init__(self, headless: bool = False):
        self.stealth = StealthConfig()

    async def __aenter__(self) -> "BrowserManager"
    async def __aexit__(self, *args) -> None
    async def new_page(self) -> Page:
        # 1. 使用 stealth 指纹创建 context
        # 2. 创建 page
        # 3. 对 page 应用 stealth 补丁
        # 4. 返回 page
        ...
    async def save_state(self) -> None      # 保存登录态到 auth_state/
    async def load_state(self) -> bool       # 加载已有登录态
```

### 3.3 登录与会话管理模块 — `auth.py`

**职责**：处理首次登录和登录态复用

**流程**：

```
启动 → 检查 auth_state/state.json 是否存在
  ├── 存在 → 加载 state → 访问首页 → 检测是否仍然有效
  │     ├── 有效 → 继续采集
  │     └── 失效 → 进入手动登录流程
  └── 不存在 → 进入手动登录流程

手动登录流程：
  1. 打开小红书登录页（headed 模式）
  2. 控制台提示用户手动扫码/输入登录
  3. 检测到登录成功后（URL 变化或特定元素出现）
  4. 保存 storage_state 到 auth_state/state.json
```

**关键设计**：
- 登录态文件路径：`auth_state/state.json`
- 登录成功检测：等待页面出现已登录标识元素
- 超时设置：手动登录等待 120 秒

### 3.4 搜索结果采集模块 — `search.py`

**职责**：按关键词搜索，采集结果列表

**采集流程**：

```
1. 导航到小红书搜索页
2. 输入关键词，触发搜索
3. 等待搜索结果加载
4. 滚动页面加载更多结果（按配置的页数/条数）
5. 解析每条搜索结果卡片
6. 收集笔记 URL 列表，供后续详情采集
```

**采集字段**：

| 字段 | 说明 |
|------|------|
| `note_id` | 笔记 ID（从 URL 提取） |
| `title` | 笔记标题 |
| `author` | 作者昵称 |
| `author_id` | 作者 ID |
| `cover_url` | 封面图片 URL |
| `likes` | 点赞数 |
| `note_url` | 笔记详情页 URL |
| `note_type` | 笔记类型（图文/视频） |

**翻页策略**：
- 小红书搜索结果为瀑布流（无限滚动）
- 通过 `page.mouse.wheel()` 或 `page.evaluate("window.scrollBy()")` 模拟滚动
- 每次滚动后等待新内容加载（监测 DOM 元素数量变化）
- 达到目标条数或无新内容时停止

### 3.5 笔记详情采集模块 — `note.py`

**职责**：进入笔记详情页，采集完整信息

**采集字段**：

| 字段 | 说明 |
|------|------|
| `note_id` | 笔记 ID |
| `title` | 标题 |
| `content` | 正文内容（纯文本） |
| `author` | 作者昵称 |
| `author_id` | 作者 ID |
| `publish_time` | 发布时间 |
| `likes` | 点赞数 |
| `collects` | 收藏数 |
| `comments_count` | 评论数 |
| `shares` | 分享数 |
| `tags` | 标签列表 |
| `images` | 图片 URL 列表 |
| `note_type` | 图文 / 视频 |
| `video_url` | 视频 URL（视频笔记） |

**采集流程**：

```
1. 打开笔记详情页 URL
2. 等待页面核心内容加载完成
3. 解析页面 DOM，提取上述字段
4. 触发评论采集（调用 comment 模块）
5. 随机延迟后进入下一条笔记
```

### 3.6 评论采集模块 — `comment.py`

**职责**：在笔记详情页采集 Top 20 评论

**采集字段**：

| 字段 | 说明 |
|------|------|
| `comment_id` | 评论 ID |
| `note_id` | 所属笔记 ID |
| `user_name` | 评论者昵称 |
| `user_id` | 评论者 ID |
| `content` | 评论内容 |
| `likes` | 评论点赞数 |
| `time` | 评论时间 |
| `ip_location` | IP 属地 |

**采集流程**：

```
1. 在笔记详情页定位评论区域
2. 滚动评论区加载更多（若不足 20 条）
3. 按顺序提取前 20 条评论
4. 解析每条评论的 DOM 元素
```

### 3.7 数据解析模块 — `parser.py`

**职责**：将页面 DOM 元素转换为结构化数据

- 提供各页面类型的解析函数
- 处理数字格式转换（如 "1.2万" → 12000）
- 处理缺失字段的默认值
- 清洗文本内容（去除多余空白、特殊字符）

```python
def parse_search_card(element: ElementHandle) -> dict
def parse_note_detail(page: Page) -> dict
def parse_comment(element: ElementHandle) -> dict
def normalize_count(text: str) -> int          # "1.2万" → 12000
```

### 3.8 数据存储模块 — `storage.py`

**职责**：将采集结果持久化到本地

**存储格式**：

```
data/
├── raw/
│   └── {keyword}_{timestamp}.json          # 完整原始数据
└── processed/
    ├── search_results_{keyword}.csv         # 搜索结果汇总
    ├── notes_{keyword}.csv                  # 笔记详情汇总
    └── comments_{keyword}.csv               # 评论汇总
```

- JSON：保留完整结构，方便程序读取
- CSV：扁平化表格，方便 Excel / Pandas 分析

---

## 4. 配置文件设计

`config/settings.yaml`：

```yaml
# 采集配置
crawler:
  keywords:                     # 搜索关键词列表
    - "关键词1"
    - "关键词2"
  max_notes_per_keyword: 20     # 每个关键词最多采集笔记数
  max_comments_per_note: 20     # 每条笔记最多采集评论数
  scroll_pause: 1.5             # 滚动后等待时间（秒）
  page_load_timeout: 30         # 页面加载超时（秒）

# 延迟配置（模拟人类行为，降低风险）
delay:
  between_notes: [2, 5]         # 笔记之间随机延迟范围（秒）
  between_searches: [3, 8]      # 搜索之间随机延迟范围（秒）
  scroll_interval: [1, 3]       # 滚动间隔随机延迟范围（秒）

# 浏览器配置
browser:
  headless: false               # 是否无头模式（调试时建议 false）
  viewport_width: 1280
  viewport_height: 800

# 存储配置
storage:
  output_dir: "data"
  save_raw_json: true           # 是否保存原始 JSON
  save_csv: true                # 是否保存 CSV
```

---

## 5. 采集主流程

```
┌─────────────┐
│   启动程序   │
└──────┬──────┘
       │
       ▼
┌─────────────┐     ┌──────────────┐
│  加载配置    │────▶│  初始化浏览器  │
└─────────────┘     └──────┬───────┘
                           │
                           ▼
                    ┌─────────────┐    失败    ┌──────────────┐
                    │ 加载登录态   │──────────▶│  手动登录流程  │
                    └──────┬──────┘           └──────┬───────┘
                           │ 成功                     │
                           ▼                          │
                    ┌─────────────┐◀──────────────────┘
                    │  保存登录态  │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ 关键词 1  │ │ 关键词 2  │ │ 关键词 N  │
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             ▼            ▼            ▼
        ┌──────────────────────────────────┐
        │       搜索 → 翻页 → 采集列表      │
        └──────────────┬───────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │  遍历笔记 URL → 采集详情 + 评论   │
        │  （每条笔记之间随机延迟）           │
        └──────────────┬───────────────────┘
                       │
                       ▼
        ┌──────────────────────────────────┐
        │     数据存储（JSON + CSV）         │
        └──────────────────────────────────┘
```

---

## 6. 反爬与稳定性策略

### 6.1 反检测层（三层防护）

```
┌──────────────────────────────────────────────────┐
│  Layer 3: 行为层                                  │
│  - 随机延迟（模拟人类操作节奏）                     │
│  - 随机滚动幅度（非固定像素）                       │
│  - 鼠标移动轨迹（非瞬移）                          │
│  - 随机 viewport 微调                              │
├──────────────────────────────────────────────────┤
│  Layer 2: 指纹层 — browserforge                   │
│  - 真实 User-Agent（匹配 OS + 浏览器版本）         │
│  - 屏幕分辨率 / 色深 / 像素比                      │
│  - WebGL 渲染器 / 供应商信息                       │
│  - Canvas 指纹一致性                               │
│  - 语言 / 时区 / 平台属性                          │
├──────────────────────────────────────────────────┤
│  Layer 1: 环境层 — playwright-stealth              │
│  - 删除 navigator.webdriver                        │
│  - 修补 chrome.runtime                             │
│  - 伪装 Permissions API                            │
│  - 清除 HeadlessChrome UA 标识                     │
│  - 修补 iframe contentWindow                       │
│  - 修补 navigator.plugins                          │
└──────────────────────────────────────────────────┘
```

### 6.2 稳定性策略

| 策略 | 实现方式 |
|------|----------|
| 随机延迟 | 每次操作间加入 `random.uniform(min, max)` 延迟 |
| 指纹轮换 | 每次启动浏览器生成新指纹，避免被关联追踪 |
| 登录态复用 | `storage_state` 持久化，避免频繁登录 |
| 错误重试 | 页面加载失败时重试 2 次，超过则跳过并记录 |
| 异常恢复 | 采集中断时已采集数据不丢失（实时写入） |
| 速率控制 | 可配置的延迟参数，按需调整采集速度 |
| 检测感知 | 遇到验证码/风控页面时暂停并通知用户 |

---

## 7. 实现步骤（开发顺序）

### Phase 1：基础框架 + 反检测
- [x] 初始化项目依赖（playwright, playwright-stealth, browserforge, pyyaml）
- [x] 实现 `stealth.py` — 反检测配置（stealth 补丁 + 指纹生成）
- [x] 实现 `browser.py` — 浏览器生命周期管理（集成 stealth）
- [x] 实现 `auth.py` — 登录与会话持久化
- [x] 验证：浏览器通过反检测测试站点（如 bot.sannysoft.com）— `scripts/verify_stealth.py`
- [x] 验证：能手动登录并保存/复用登录态 — `scripts/verify_login.py`

### Phase 2：搜索采集
- [x] 实现 `search.py` — 搜索结果列表采集
- [x] 实现 `parser.py` — 搜索卡片解析
- [x] 实现 `storage.py` — JSON / CSV 存储
- [x] 验证：能按关键词搜索并导出搜索结果

### Phase 3：详情与评论
- [x] 实现 `note.py` — 笔记详情采集
- [x] 实现 `comment.py` — 评论采集
- [x] 补充 `parser.py` — 详情页和评论解析
- [x] 扩展 `storage.py` — 笔记详情和评论存储
- [x] 验证：能完整采集笔记详情 + Top 20 评论 — `scripts/verify_note.py`

### Phase 4：整合与优化
- [ ] 实现 `main.py` — 串联完整采集流程
- [ ] 实现配置文件加载（`settings.yaml`）
- [ ] 添加日志输出（采集进度、错误信息）
- [ ] 端到端测试：关键词 → 搜索 → 详情 → 评论 → 导出

---

## 8. 依赖清单

```
playwright              # 浏览器自动化核心
playwright-stealth      # 反检测：消除自动化痕迹
browserforge            # 反检测：真实浏览器指纹生成
pyyaml                  # 配置文件解析
```

安装命令：

```bash
uv add playwright playwright-stealth browserforge pyyaml
uv run playwright install chromium
```

---

## 9. 注意事项

1. **仅供个人使用** — 此工具仅用于个人账号的数据采集，不用于商业用途或大规模爬取
2. **合理频率** — 通过延迟配置控制采集速度，避免对平台造成压力
3. **登录态安全** — `auth_state/` 目录已加入 `.gitignore`，不会提交到代码仓库
4. **数据安全** — `data/` 目录建议也加入 `.gitignore`
