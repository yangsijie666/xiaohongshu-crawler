"""
小红书数据采集器 — 入口

运行方式：
    uv run python main.py

当前阶段（Phase 1）：验证浏览器启动、反检测配置、登录态管理。
"""

import asyncio
import logging
from pathlib import Path

import yaml

from src.auth import ensure_logged_in
from src.browser import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config/settings.yaml") -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


async def main() -> None:
    config = load_config()
    headless = config.get("browser", {}).get("headless", False)

    logger.info("启动小红书采集器（Phase 1 — 基础框架验证）")

    async with BrowserManager(headless=headless) as bm:
        logged_in = await ensure_logged_in(bm)
        if not logged_in:
            logger.error("登录失败，退出")
            return

        logger.info("登录态就绪，可以开始采集")
        # Phase 2+ 将在此处调用 search / note / comment 模块


if __name__ == "__main__":
    asyncio.run(main())
