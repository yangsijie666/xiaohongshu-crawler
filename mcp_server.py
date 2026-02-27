"""
小红书数据采集 MCP 服务入口

通过 MCP 协议将采集能力暴露为 AI 助手可调用的工具，支持：
  - Claude Desktop / Code / Cursor 等任意 MCP 客户端

当前实现（Phase A-D）：
  - check_login_status：检查登录状态
  - search_notes：关键词搜索笔记
  - get_note_detail：采集笔记详情 + 评论
  - crawl_keyword：完整采集流程
  - get_saved_data：查询本地已保存数据

Phase D 增强：
  - 工具超时控制（search 120s / detail 90s / crawl 600s）
  - 日志输出到文件（stdout 被 MCP stdio 占用）
  - 统一结构化错误格式透传

启动方式：
  # 本地开发调试（MCP Inspector）
  mcp dev mcp_server.py

  # 直接运行
  uv run python mcp_server.py

配置 Claude Desktop / Code：
  参考 claude_mcp_config.example.json

注意：
  MCP stdio 模式下 stdout 被协议占用，日志必须输出到 stderr。
  首次使用前请运行 `uv run python scripts/verify_login.py` 完成登录。
"""

from __future__ import annotations

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import AsyncGenerator

from mcp.server.fastmcp import FastMCP

from src.errors import invalid_input_error, timeout_error
from src.session import CrawlerSession

# MCP stdio 模式下 stdout 被协议占用，日志输出到 stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)


# ============================================================
# Phase D: 工具超时控制（秒）
# ============================================================

TOOL_TIMEOUTS: dict[str, int] = {
    "search_notes": 120,
    "get_note_detail": 90,
    "crawl_keyword": 600,
}


# ============================================================
# Phase D: 日志文件输出
# ============================================================

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_LOG_DIR_DEFAULT = Path("logs")


def setup_file_logging(
    log_dir: Path = _LOG_DIR_DEFAULT,
    max_bytes: int = 5 * 1024 * 1024,
    backup_count: int = 3,
) -> None:
    """配置日志文件输出（RotatingFileHandler）。

    MCP stdio 模式下 stdout 被协议占用，关键日志同时写入文件便于排查问题。

    Args:
        log_dir: 日志目录（默认 logs/）
        max_bytes: 单个日志文件大小上限（默认 5MB）
        backup_count: 保留的历史日志文件数（默认 3）
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_dir / "mcp_server.log",
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))

    root_logger = logging.getLogger()
    # 确保 root logger 至少记录 INFO 级别（MCP 进程中 basicConfig 可能未生效）
    if root_logger.level > logging.INFO:
        root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    logger.info("日志文件输出已启用：%s", log_dir / "mcp_server.log")


# ---- 全局会话单例（MCP 进程生命周期内持续运行）----
_session = CrawlerSession(headless=True)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    """MCP 服务启停钩子：管理浏览器生命周期。

    服务启动时初始化浏览器并启用文件日志，服务关闭时释放资源。
    """
    # Phase D: 启动时配置文件日志
    setup_file_logging()

    logger.info("rednote-crawler MCP 服务启动中...")
    await _session.start()
    logger.info("rednote-crawler MCP 服务就绪（浏览器已启动）")
    try:
        yield
    finally:
        logger.info("rednote-crawler MCP 服务关闭中...")
        await _session.stop()
        logger.info("rednote-crawler MCP 服务已关闭")


# ---- 创建 MCP 服务实例 ----
mcp = FastMCP("rednote-crawler", lifespan=lifespan)


# ============================================================
# Phase D: 超时包装工具
# ============================================================


async def _with_timeout(coro, tool_name: str) -> dict:
    """为异步操作添加超时控制。

    Args:
        coro: 待执行的协程
        tool_name: 工具名称（用于错误消息和超时配置查找）

    Returns:
        正常结果或超时错误字典
    """
    timeout_seconds = TOOL_TIMEOUTS.get(tool_name, 120)
    try:
        return await asyncio.wait_for(coro, timeout=timeout_seconds)
    except asyncio.TimeoutError:
        logger.error("%s 操作超时（%d 秒）", tool_name, timeout_seconds)
        return timeout_error(tool_name=tool_name, timeout_seconds=timeout_seconds).to_dict()


# ============================================================
# Phase A 工具
# ============================================================


@mcp.tool()
async def check_login_status() -> dict:
    """检查小红书登录状态。

    返回当前浏览器运行状态和登录状态。
    如果未登录，请先运行 `uv run python scripts/verify_login.py` 完成扫码登录，
    然后重启本 MCP 服务。

    预计耗时：5-10 秒（需访问小红书首页）

    Returns:
        logged_in (bool): 是否已成功登录小红书
        browser_running (bool): 浏览器是否正在运行
        message (str): 状态说明及操作建议
    """
    logger.info("工具调用：check_login_status")
    result = await _session.check_login_status()
    logger.info("登录状态：%s", result)
    return result


# ============================================================
# Phase B 工具
# ============================================================


@mcp.tool()
async def search_notes(keyword: str, max_count: int = 20) -> dict:
    """按关键词搜索小红书笔记，返回摘要列表。

    Args:
        keyword: 搜索关键词（必填，不能为空）
        max_count: 最多返回笔记数（可选，默认 20，范围 1-50）

    Returns:
        keyword (str): 搜索关键词
        count (int): 实际返回条数
        results (list): 笔记摘要列表，每条包含
            note_id / title / author / likes / note_url 等字段

    预计耗时：30-90 秒（含页面加载 + 滚动）。超时限制：120 秒。
    """
    # 输入验证：keyword 不能为空
    stripped_keyword = keyword.strip()
    if not stripped_keyword:
        return invalid_input_error(field="keyword", reason="不能为空").to_dict()

    # 边界截断：max_count 限制在 1-50
    clamped_max_count = max(1, min(max_count, 50))

    logger.info("工具调用：search_notes（keyword=%s，max_count=%d）", stripped_keyword, clamped_max_count)

    # Phase D: 超时控制
    result = await _with_timeout(
        _session.search_notes(keyword=stripped_keyword, max_count=clamped_max_count),
        tool_name="search_notes",
    )
    logger.info("search_notes 完成：count=%s", result.get("count", result.get("code", 0)))
    return result


@mcp.tool()
async def get_note_detail(note_url: str, max_comments: int = 20) -> dict:
    """采集单篇小红书笔记的详情和评论。

    Args:
        note_url: 笔记详情页 URL（必填），格式：
            https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...
        max_comments: 最多采集评论数（可选，默认 20，范围 0-50）

    Returns:
        成功时返回笔记详情字典，包含：
            note_id / title / content / author / likes / collects /
            tags / images / comments 等字段
        失败时返回 {"error": True, "code": str, "message": str, "action": str}

    预计耗时：15-60 秒（含页面加载 + 评论滚动）。超时限制：90 秒。
    """
    # 输入验证：URL 不能为空
    if not note_url.strip():
        return invalid_input_error(field="note_url", reason="不能为空").to_dict()

    # 边界截断：max_comments 限制在 0-50
    clamped_max_comments = max(0, min(max_comments, 50))

    # 日志中截去 xsec_token 等查询参数，避免敏感 token 写入日志
    safe_url = note_url.split("?")[0]
    logger.info("工具调用：get_note_detail（url=%s，max_comments=%d）", safe_url, clamped_max_comments)

    # Phase D: 超时控制
    result = await _with_timeout(
        _session.get_note_detail(note_url=note_url, max_comments=clamped_max_comments),
        tool_name="get_note_detail",
    )

    # 防御性检查（session 层已保证返回 dict，此处作兜底）
    if result is None:
        from src.errors import crawl_failed_error
        return crawl_failed_error(f"无法采集笔记详情：{safe_url}").to_dict()

    logger.info("get_note_detail 完成：note_id=%s", result.get("note_id", result.get("code", "unknown")))
    return result


# ============================================================
# Phase C 工具
# ============================================================

# MCP 资源路径常量（模块级，供测试 patch）
_CONFIG_PATH = Path("config/settings.yaml")
_DATA_DIR = Path("data")


@mcp.tool()
async def crawl_keyword(keyword: str, max_notes: int = 10, max_comments: int = 20) -> dict:
    """完整采集流程：搜索关键词 → 采集笔记详情 + 评论 → 保存到本地文件。

    Args:
        keyword: 搜索关键词（必填，不能为空）
        max_notes: 最多采集笔记数（可选，默认 10，范围 1-20）
        max_comments: 每条笔记最多采集评论数（可选，默认 20，范围 0-50）

    Returns:
        keyword / search_count / detail_count / total_comments / summary
        失败时返回 {"error": True, "code": str, "message": str, "action": str}

    预计耗时：2-15 分钟（取决于笔记数量）。超时限制：600 秒。
    建议先用 search_notes 验证关键词再调用本工具。
    """
    stripped_keyword = keyword.strip()
    if not stripped_keyword:
        return invalid_input_error(field="keyword", reason="不能为空").to_dict()

    # 边界截断
    clamped_max_notes = max(1, min(max_notes, 20))
    clamped_max_comments = max(0, min(max_comments, 50))

    logger.info(
        "工具调用：crawl_keyword（keyword=%s，max_notes=%d，max_comments=%d）",
        stripped_keyword, clamped_max_notes, clamped_max_comments,
    )

    # Phase D: 超时控制
    result = await _with_timeout(
        _session.crawl_keyword(
            keyword=stripped_keyword,
            max_notes=clamped_max_notes,
            max_comments=clamped_max_comments,
        ),
        tool_name="crawl_keyword",
    )
    logger.info("crawl_keyword 完成：%s", result.get("summary", result.get("message", "")))
    return result


@mcp.tool()
async def get_saved_data(keyword: str = "") -> dict:
    """查询本地已保存的采集数据文件列表。

    Args:
        keyword: 关键词过滤（可选，不区分大小写，模糊匹配；不传或空字符串表示返回全部文件）

    Returns:
        files: 文件列表，每条包含 path / keyword / created_at / size_bytes

    预计耗时：< 1 秒（本地文件系统扫描）
    """
    filter_keyword = keyword.strip() or None
    logger.info("工具调用：get_saved_data（keyword=%s）", filter_keyword or "(全部)")
    result = await _session.get_saved_data(keyword=filter_keyword)
    logger.info("get_saved_data 完成：%d 个文件", len(result.get("files", [])))
    return result


# ============================================================
# Phase C 资源端点
# ============================================================


@mcp.resource("rednote://config")
async def get_config_resource() -> str:
    """读取当前 settings.yaml 配置（只读）。

    返回 YAML 格式的配置文本，供 AI 了解当前采集参数设置（关键词、延迟、存储等）。
    """
    if not _CONFIG_PATH.exists():
        return f"配置文件不存在：{_CONFIG_PATH}。请确保 config/settings.yaml 已创建。"
    return _CONFIG_PATH.read_text(encoding="utf-8")


@mcp.resource("rednote://data/{filename}")
async def get_data_resource(filename: str) -> str:
    """读取指定本地数据文件内容（只读）。

    在 data/raw/ 和 data/processed/ 子目录中查找文件并返回内容。

    Args:
        filename: 数据文件名（如 Python教程_20240315_143022.json），不含路径

    Returns:
        文件的文本内容（JSON 格式），或错误消息

    安全限制：只允许访问 data/ 目录下的文件，拒绝路径穿越（../）攻击。
    """
    # 安全检查：拒绝路径穿越和子目录访问
    if ".." in filename or "/" in filename or "\\" in filename:
        return f"无效的文件名（不允许路径穿越或子目录访问）：{filename}"

    # 在 raw 和 processed 两个子目录中查找
    for subdir in ("raw", "processed"):
        file_path = _DATA_DIR / subdir / filename
        if file_path.exists() and file_path.is_file():
            return file_path.read_text(encoding="utf-8", errors="replace")

    return (
        f"文件不存在：{filename}。"
        "请先使用 crawl_keyword 或 search_notes 采集数据，"
        "或通过 get_saved_data 查看已有文件列表。"
    )


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
