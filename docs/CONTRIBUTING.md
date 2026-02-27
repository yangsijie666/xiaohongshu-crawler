# 贡献指南

## 开发环境搭建

### 前置条件

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) 包管理器

### 安装步骤

```bash
# 克隆仓库
git clone <repo-url> && cd rednote-crawler

# 安装依赖
uv sync

# 安装 Chromium
uv run playwright install chromium
```

<!-- AUTO-GENERATED: commands-reference -->
## 可用命令

| 命令 | 说明 |
|------|------|
| `uv sync` | 安装/同步依赖 |
| `uv run python main.py` | 运行完整采集 |
| `uv run python scripts/verify_stealth.py` | 反检测验证 |
| `uv run python scripts/verify_login.py` | 登录验证 |
| `uv run python scripts/verify_search.py` | 搜索采集验证 |
| `uv run python scripts/verify_note.py` | 笔记详情+评论验证 |
| `uv run python scripts/verify_e2e.py` | 端到端集成验证 |
| `uv add <package>` | 添加新依赖 |
<!-- /AUTO-GENERATED: commands-reference -->

## 验证测试

项目使用 `scripts/` 目录下的验证脚本进行测试。新增功能后，请运行相关验证脚本确认功能正确。

```bash
# 验证反检测
uv run python scripts/verify_stealth.py

# 验证登录
uv run python scripts/verify_login.py

# 验证搜索采集
uv run python scripts/verify_search.py

# 验证笔记详情+评论
uv run python scripts/verify_note.py

# 端到端集成验证
uv run python scripts/verify_e2e.py
```

### 编写验证脚本

新模块完成后，请在 `scripts/` 目录下添加对应验证脚本：

- 文件名格式: `verify_<模块名>.py`
- 需覆盖: 正常流程、边界条件、错误恢复
- 使用 `asyncio.run()` 作为入口
- 通过 `logging` 输出验证结果

## 代码规范

- 遵循 PEP 8 风格
- 使用 type hints
- 模块级 docstring + 中文行内注释
- 使用 `pathlib.Path` 管理路径
- 使用 `logging` 模块记录日志
- 捕获特定异常，优雅降级
- 使用 `TYPE_CHECKING` 守卫避免运行时循环导入

## Git 工作流

### Commit 格式

```
<type>(<scope>): 中文描述
```

类型: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`

示例:
- `feat(search): 新增搜索结果去重逻辑`
- `fix(parser): 修复评论解析空指针异常`

### 分支策略

- 主分支: `main`
- 功能分支: `feat/<功能名>`

## PR 提交清单

- [ ] 代码遵循项目编码规范
- [ ] 新增功能有对应验证脚本
- [ ] 验证脚本运行通过
- [ ] Commit message 遵循 Conventional Commits 格式
- [ ] 无硬编码密钥或敏感信息
