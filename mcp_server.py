"""
小红书数据采集 MCP 服务入口

通过 MCP 协议将采集能力暴露为 AI 助手可调用的工具，支持：
  - Claude Desktop / Code / Cursor 等任意 MCP 客户端

当前实现（Phase A）：
  - check_login_status：检查登录状态

后续规划（Phase B-C）：
  - search_notes：关键词搜索笔记
  - get_note_detail：采集笔记详情 + 评论
  - crawl_keyword：完整采集流程
  - get_saved_data：查询本地已保存数据

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

import logging
import sys
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from mcp.server.fastmcp import FastMCP

from src.session import CrawlerSession

# MCP stdio 模式下 stdout 被协议占用，日志输出到 stderr
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger(__name__)

# ---- 全局会话单例（MCP 进程生命周期内持续运行）----
_session = CrawlerSession(headless=True)


@asynccontextmanager
async def lifespan(server: FastMCP) -> AsyncGenerator[None, None]:
    """MCP 服务启停钩子：管理浏览器生命周期。

    服务启动时初始化浏览器，服务关闭时释放资源。
    """
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

    预计耗时：30-90 秒（含页面加载 + 滚动）
    """
    # 输入验证：keyword 不能为空
    stripped_keyword = keyword.strip()
    if not stripped_keyword:
        return {"error": True, "message": "keyword 不能为空"}

    # 边界截断：max_count 限制在 1-50
    clamped_max_count = max(1, min(max_count, 50))

    logger.info("工具调用：search_notes（keyword=%s，max_count=%d）", stripped_keyword, clamped_max_count)
    result = await _session.search_notes(keyword=stripped_keyword, max_count=clamped_max_count)
    logger.info("search_notes 完成：count=%s", result.get("count", 0))
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
        失败时返回 {"error": True, "message": str}

    预计耗时：15-60 秒（含页面加载 + 评论滚动）
    """
    # 输入验证：URL 不能为空
    if not note_url.strip():
        return {"error": True, "message": "note_url 不能为空"}

    # 边界截断：max_comments 限制在 0-50
    clamped_max_comments = max(0, min(max_comments, 50))

    # 日志中截去 xsec_token 等查询参数，避免敏感 token 写入日志
    safe_url = note_url.split("?")[0]
    logger.info("工具调用：get_note_detail（url=%s，max_comments=%d）", safe_url, clamped_max_comments)

    result = await _session.get_note_detail(note_url=note_url, max_comments=clamped_max_comments)

    # 防御性检查（session 层已保证返回 dict，此处作兜底）
    if result is None:
        return {"error": True, "message": f"无法采集笔记详情，请检查 URL 是否有效：{safe_url}"}

    logger.info("get_note_detail 完成：note_id=%s", result.get("note_id", "unknown"))
    return result


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
