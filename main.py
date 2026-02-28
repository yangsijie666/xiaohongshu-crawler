"""
小红书数据采集器 — 主入口

完整采集流程：
  1. 加载配置（config/settings.yaml）
  2. 初始化浏览器（BrowserManager + 反检测）
  3. 确保登录态就绪（复用或手动登录）
  4. 遍历关键词列表：
     a. 搜索 → 采集笔记摘要列表
     b. 逐条采集笔记详情 + 评论
     c. 统一保存数据（JSON + Excel）
  5. 关键词之间随机延迟，模拟人类行为

运行方式：
    uv run python main.py
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
from pathlib import Path

import yaml

from src.auth import ensure_logged_in
from src.browser import BrowserManager
from src.note import fetch_note_details
from src.search import search_notes
from src.storage import Storage

# ---- 日志配置 ----
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)


def load_config(path: str = "config/settings.yaml") -> dict:
    """加载 YAML 配置文件。

    Args:
        path: 配置文件路径（相对于项目根目录）

    Returns:
        配置字典

    Raises:
        SystemExit: 配置文件不存在或解析失败时退出
    """
    config_path = Path(path)
    if not config_path.exists():
        logger.error("配置文件不存在：%s", config_path)
        sys.exit(1)
    try:
        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        logger.info("配置文件加载成功：%s", config_path)
        return config
    except yaml.YAMLError as e:
        logger.error("配置文件解析失败：%s", e)
        sys.exit(1)


async def crawl_keyword(
    bm: BrowserManager,
    keyword: str,
    crawler_cfg: dict,
    delay_cfg: dict,
    storage: Storage,
) -> None:
    """采集单个关键词的完整流程：搜索 → 详情 → 评论 → 存储。

    Args:
        bm: 已初始化且登录的 BrowserManager 实例
        keyword: 搜索关键词
        crawler_cfg: settings.yaml 中的 crawler 节点
        delay_cfg: settings.yaml 中的 delay 节点
        storage: Storage 实例
    """
    logger.info("=" * 60)
    logger.info("开始采集关键词：%s", keyword)
    logger.info("=" * 60)

    max_notes = crawler_cfg.get("max_notes_per_keyword", 20)
    max_comments = crawler_cfg.get("max_comments_per_note", 20)
    scroll_pause = crawler_cfg.get("scroll_pause", 1.5)
    scroll_interval = tuple(delay_cfg.get("scroll_interval", [1.0, 3.0]))
    between_notes = tuple(delay_cfg.get("between_notes", [2.0, 5.0]))

    # ---- Step 1: 搜索 ----
    logger.info("[Step 1/2] 搜索笔记列表（关键词：%s，目标：%d 条）", keyword, max_notes)
    search_results = await search_notes(
        bm,
        keyword=keyword,
        max_count=max_notes,
        scroll_pause=scroll_pause,
        scroll_interval=scroll_interval,
    )

    if not search_results:
        logger.warning("搜索结果为空，跳过当前关键词：%s", keyword)
        return

    logger.info("搜索完成：获得 %d 条笔记摘要", len(search_results))

    # ---- Step 2: 采集详情 + 评论 ----
    logger.info(
        "[Step 2/2] 批量采集笔记详情 + 评论（%d 条笔记，每条最多 %d 条评论）",
        len(search_results),
        max_comments,
    )
    note_details = await fetch_note_details(
        bm,
        search_results=search_results,
        max_comments=max_comments,
        delay_range=between_notes,
        scroll_pause=scroll_pause,
        scroll_interval=scroll_interval,
    )

    # ---- 保存数据（JSON + Excel） ----
    storage.save_all(keyword, search_results, note_details)

    # 统计本次采集结果
    total_comments = sum(len(note.get("comments", [])) for note in note_details)
    logger.info(
        "关键词 [%s] 采集完成：笔记 %d 条，评论 %d 条",
        keyword,
        len(note_details),
        total_comments,
    )


async def main() -> None:
    """主函数：加载配置 → 初始化 → 登录 → 遍历关键词采集。"""
    config = load_config()

    crawler_cfg: dict = config.get("crawler", {})
    delay_cfg: dict = config.get("delay", {})
    browser_cfg: dict = config.get("browser", {})
    storage_cfg: dict = config.get("storage", {})

    keywords: list[str] = crawler_cfg.get("keywords", [])
    if not keywords:
        logger.error("配置文件中未设置关键词（crawler.keywords），退出")
        sys.exit(1)

    between_searches = tuple(delay_cfg.get("between_searches", [3.0, 8.0]))
    headless: bool = browser_cfg.get("headless", False)

    logger.info("小红书数据采集器启动")
    logger.info("关键词列表（%d 个）：%s", len(keywords), keywords)

    # 初始化存储
    storage = Storage(storage_cfg)

    # 初始化浏览器
    async with BrowserManager(headless=headless) as bm:
        # 确保登录态就绪
        logger.info("检查登录状态...")
        logged_in = await ensure_logged_in(bm)
        if not logged_in:
            logger.error("登录失败，退出")
            sys.exit(1)

        logger.info("登录态就绪，开始采集流程")

        # 遍历关键词
        for idx, keyword in enumerate(keywords):
            try:
                await crawl_keyword(
                    bm,
                    keyword=keyword,
                    crawler_cfg=crawler_cfg,
                    delay_cfg=delay_cfg,
                    storage=storage,
                )
            except Exception as e:
                logger.error("关键词 [%s] 采集异常：%s", keyword, e, exc_info=True)

            # 关键词之间随机延迟（最后一个不需要）
            if idx < len(keywords) - 1:
                delay = random.uniform(*between_searches)
                logger.info(
                    "延迟 %.1f 秒后处理下一个关键词 [%s]...",
                    delay,
                    keywords[idx + 1],
                )
                await asyncio.sleep(delay)

    logger.info("=" * 60)
    logger.info("所有关键词采集完成！共处理 %d 个关键词", len(keywords))
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
