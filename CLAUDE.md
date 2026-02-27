# CLAUDE.md — rednote-crawler

## 项目概述

小红书 (Xiaohongshu) 数据采集框架，基于 Playwright 实现真实浏览器自动化，具备双层反检测能力（playwright-stealth + browserforge）。

当前处于 **Phase 4 完成** 状态（集成 & 优化），所有阶段均已完成。

## 技术栈

- **语言:** Python 3.10+
- **包管理:** uv（非 pip）
- **浏览器自动化:** Playwright (async API)
- **反检测:** playwright-stealth + browserforge
- **配置管理:** PyYAML

## 常用命令

```bash
# 安装依赖
uv sync
uv run playwright install chromium

# 运行主程序
uv run python main.py

# 验证脚本
uv run python scripts/verify_stealth.py    # 反检测验证
uv run python scripts/verify_login.py      # 登录验证
uv run python scripts/verify_search.py     # 搜索采集验证
uv run python scripts/verify_note.py       # 笔记详情+评论验证

# 添加依赖
uv add <package-name>
```

## 项目结构

```
src/
├── stealth.py     # 反检测配置（指纹生成 + stealth 注入）
├── browser.py     # Playwright 浏览器生命周期管理 (BrowserManager)
├── auth.py        # 登录 & 会话管理
├── search.py      # 搜索结果采集（瀑布流滚动）
├── note.py        # 笔记详情采集（含重试逻辑）
├── comment.py     # 评论采集（Top N）
├── parser.py      # 页面数据解析（搜索卡片 / 详情 / 评论）
└── storage.py     # 数据存储（JSON + Excel/xlsx）
scripts/           # 验证脚本
config/settings.yaml  # 采集配置（关键词、延迟、浏览器参数）
main.py            # 入口文件
```

## 架构要点

- **异步优先:** 所有 I/O 操作使用 async/await
- **BrowserManager:** 异步上下文管理器，管理浏览器生命周期
- **会话持久化:** 登录状态保存至 `auth_state/state.json`，下次启动自动恢复
- **双层反检测:** 环境级（navigator.webdriver 移除）+ 指纹级（WebGL/Canvas）
- **配置外置:** YAML 配置文件，支持不改代码调整参数

## 工作流程

### 复杂任务（多文件、新功能、架构变更）

1. **理解需求** — 先读相关代码和文档，找到相似实现案例，确认技术选型
2. **规划方案** — 使用 EnterPlanMode 进行方案设计，用户确认后再动手
3. **分步实现** — 使用 TodoWrite 跟踪进度，小步修改，每步可验证
4. **验证交付** — 运行验证脚本确认功能正确，报告结果

### 简单任务（单文件修改、Bug 修复）

直接读代码 → 修改 → 验证，无需规划流程。

### 通用原则

- 实现前必须先读相关代码，禁止对未读代码提建议
- 复杂任务用 Task 工具并行探索代码库，避免串行低效搜索
- 连续 3 次相同错误必须暂停，重新评估策略
- 禁止假设或猜测，结论必须基于代码或文档证据

## 编码策略

- 优先复用官方 SDK 和主流生态库，避免不必要的自研
- 发现缺陷优先修复，再扩展新功能
- 小步修改，每次变更保持可运行可验证
- 禁止占位或骨架实现，提交完整功能代码
- 及时删除过时内容与冗余实现，不保留无用的向后兼容
- 遵守 SOLID 原则，每个函数/类单一责任
- 禁止过早抽象，重复 3 次以上再考虑通用化
- 禁止"聪明"技巧，可读性优先

## 代码规范

- 遵循 PEP 8，使用 type hints
- 模块级 docstring + 中文行内注释（描述意图、约束与使用方式）
- 使用 `pathlib.Path` 管理路径
- 使用 `logging` 模块记录日志（格式: `%(asctime)s [%(levelname)s] %(name)s: %(message)s`）
- 异常处理: 捕获特定异常，优雅降级
- `TYPE_CHECKING` 守卫避免运行时循环导入
- 遵循既有代码风格，包括导入顺序、命名与格式化

## 测试与验证

- 当前验证方式：`scripts/` 目录下的验证脚本（verify_stealth.py、verify_login.py）
- 新模块完成后编写对应验证脚本，放入 `scripts/`
- 验证脚本需覆盖：正常流程、边界条件、错误恢复
- 测试失败时报告现象、复现步骤和初步分析

## Git 规范

- **Conventional Commits:** `type(scope): 中文描述`
- 类型: `feat`, `fix`, `chore`, `docs`, `refactor`, `test`
- 主分支: `main`，功能分支: `feat/<功能名>`
- 不主动 commit，用户要求时才提交
- 不主动 push，用户要求时才推送

## 开发路线图

- **Phase 1** ✅ 基础框架（浏览器 + 反检测 + 认证）
- **Phase 2** ✅ 搜索采集（search.py, parser.py, storage.py）
- **Phase 3** ✅ 详情 & 评论（note.py, comment.py）
- **Phase 4** ✅ 集成 & 优化（完整流程、日志、端到端测试）

## 重要路径

- 计划文档: `.plan/rednote-crawler-plan.md`（技术蓝图，实现前必读）
- 配置文件: `config/settings.yaml`
- 登录状态: `auth_state/state.json`（已 gitignore）
- 数据输出: `data/`（已 gitignore）

## 沟通语言

使用中文进行所有沟通和代码注释。
