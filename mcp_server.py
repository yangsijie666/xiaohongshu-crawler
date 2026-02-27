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
# 入口
# ============================================================

if __name__ == "__main__":
    mcp.run()
