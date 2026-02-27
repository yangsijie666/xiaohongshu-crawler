"""
笔记详情采集模块

职责：
  - 接收搜索结果中的笔记 URL 列表
  - 逐条打开笔记详情页，等待核心内容加载
  - 调用 parser 解析详情字段
  - 调用 comment 模块采集评论
  - 控制采集节奏（随机延迟）

采集流程：
  1. 遍历笔记 URL 列表
  2. 打开笔记详情页，等待关键元素加载
  3. 调用 parse_note_detail() 解析页面
  4. 调用 fetch_comments() 采集评论
  5. 随机延迟后进入下一条笔记
  6. 出错时跳过当前笔记并记录日志

用法：
    async with BrowserManager() as bm:
        results = await fetch_note_details(bm, search_results, max_comments=20)
"""

from __future__ import annotations

import asyncio
import logging
import random
import re

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.browser import BrowserManager
from src.comment import fetch_comments
from src.parser import parse_note_detail

logger = logging.getLogger(__name__)

# 笔记详情页核心内容选择器（等待其中任意一个出现即认为页面加载完成）
# 真实 DOM：导航到 /explore/{id}?xsec_token=... 后，详情在 #noteContainer 内渲染
_NOTE_READY_SELECTORS = [
    "#noteContainer",
    "#detail-title",
    ".note-content",
    ".note-container",
]

# 页面加载超时（毫秒）
_PAGE_LOAD_TIMEOUT_MS = 30_000

# 等待详情内容渲染的额外时间（秒）
_RENDER_WAIT = 2.0

# 单条笔记最大重试次数
_MAX_RETRIES = 2


# 小红书笔记 URL 中 note_id 的提取正则，格式：/explore/{note_id}
_NOTE_ID_PATTERN = re.compile(r"/explore/([a-zA-Z0-9]+)")


def _extract_note_id_from_url(note_url: str) -> str | None:
    """从笔记详情页 URL 中提取 note_id。

    支持格式：https://www.xiaohongshu.com/explore/{note_id}?xsec_token=...

    Args:
        note_url: 笔记详情页完整 URL

    Returns:
        note_id 字符串，或 None（URL 格式不符）
    """
    match = _NOTE_ID_PATTERN.search(note_url)
    return match.group(1) if match else None


async def fetch_single_note(
    bm: BrowserManager,
    note_url: str,
    max_comments: int = 20,
    scroll_pause: float = 1.5,
    scroll_interval: tuple[float, float] = (1.0, 3.0),
) -> dict | None:
    """采集单篇笔记详情 + 评论（MCP 公开接口）。

    从 note_url 自动提取 note_id，再调用内部采集逻辑。
    供 MCP 工具和外部模块直接调用，无需预先知道 note_id。

    Args:
        bm: 已初始化且登录的 BrowserManager 实例
        note_url: 笔记详情页完整 URL
        max_comments: 最多采集评论数（默认 20）
        scroll_pause: 评论区滚动等待时间（秒）
        scroll_interval: 评论区额外随机延迟范围 (min, max)（秒）

    Returns:
        包含笔记详情和评论的字典，或 None（URL 无效 / 采集失败）
    """
    note_id = _extract_note_id_from_url(note_url)
    if not note_id:
        logger.error("无法从 URL 中提取 note_id，请检查 URL 格式：%s", note_url)
        return None

    return await _fetch_single_note(
        bm,
        note_id=note_id,
        note_url=note_url,
        max_comments=max_comments,
        scroll_pause=scroll_pause,
        scroll_interval=scroll_interval,
    )


async def fetch_note_details(
    bm: BrowserManager,
    search_results: list[dict],
    max_comments: int = 20,
    delay_range: tuple[float, float] = (2.0, 5.0),
    scroll_pause: float = 1.5,
    scroll_interval: tuple[float, float] = (1.0, 3.0),
) -> list[dict]:
    """批量采集笔记详情和评论。

    遍历搜索结果列表中的笔记 URL，逐条打开、解析详情、采集评论。
    每条笔记之间加入随机延迟，模拟人类浏览行为。

    Args:
        bm: 已初始化且登录的 BrowserManager 实例
        search_results: search_notes() 返回的笔记摘要列表，每条须含 note_id 和 note_url
        max_comments: 每条笔记最多采集评论数
        delay_range: 笔记之间的随机延迟范围 (min, max)（秒）
        scroll_pause: 评论滚动固定等待时间（秒）
        scroll_interval: 评论滚动额外随机延迟范围（秒）

    Returns:
        笔记详情字典列表，每条包含详情字段 + comments 子列表
    """
    total = len(search_results)
    logger.info("开始批量采集笔记详情，共 %d 条", total)

    results: list[dict] = []

    for idx, item in enumerate(search_results):
        note_id = item.get("note_id", "")
        note_url = item.get("note_url", "")

        if not note_id or not note_url:
            logger.warning("第 %d 条缺少 note_id 或 note_url，跳过", idx + 1)
            continue

        logger.info("[%d/%d] 采集笔记详情：%s", idx + 1, total, note_url)

        detail = await _fetch_single_note(
            bm,
            note_id=note_id,
            note_url=note_url,
            max_comments=max_comments,
            scroll_pause=scroll_pause,
            scroll_interval=scroll_interval,
        )

        if detail:
            results.append(detail)
            logger.info(
                "[%d/%d] 采集成功：title=%s，评论数=%d",
                idx + 1,
                total,
                detail.get("title", "")[:30],
                len(detail.get("comments", [])),
            )
        else:
            logger.warning("[%d/%d] 采集失败：note_id=%s", idx + 1, total, note_id)

        # 笔记之间随机延迟（最后一条不需要）
        if idx < total - 1:
            delay = random.uniform(*delay_range)
            logger.debug("延迟 %.1f 秒后采集下一条...", delay)
            await asyncio.sleep(delay)

    logger.info(
        "批量采集完成：成功 %d/%d 条",
        len(results),
        total,
    )
    return results


async def _fetch_single_note(
    bm: BrowserManager,
    note_id: str,
    note_url: str,
    max_comments: int,
    scroll_pause: float,
    scroll_interval: tuple[float, float],
) -> dict | None:
    """采集单条笔记的详情和评论，含重试逻辑。"""
    for attempt in range(_MAX_RETRIES + 1):
        page = await bm.new_page()
        try:
            # 导航到笔记详情页
            await page.goto(
                note_url,
                wait_until="domcontentloaded",
                timeout=_PAGE_LOAD_TIMEOUT_MS,
            )

            # 等待核心内容加载
            await _wait_for_content(page)

            # 解析详情
            detail = await parse_note_detail(page, note_id)
            if detail is None:
                logger.warning("笔记详情解析返回 None（note_id=%s）", note_id)
                return None

            # 采集评论
            comments = await fetch_comments(
                page,
                note_id=note_id,
                max_count=max_comments,
                scroll_pause=scroll_pause,
                scroll_interval=scroll_interval,
            )
            detail["comments"] = comments

            return detail

        except PlaywrightTimeoutError:
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "笔记页加载超时，重试 %d/%d（note_id=%s）",
                    attempt + 1,
                    _MAX_RETRIES,
                    note_id,
                )
                await asyncio.sleep(1)
            else:
                logger.error("笔记页加载超时，已达最大重试次数（note_id=%s）", note_id)
                return None
        except Exception as e:
            logger.error("采集笔记详情异常（note_id=%s）：%s", note_id, e, exc_info=True)
            return None
        finally:
            await page.close()

    return None


async def _wait_for_content(page: Page) -> None:
    """等待笔记详情页核心内容渲染完成。

    按优先级尝试多个选择器，任一出现即认为页面就绪。
    若全部超时，仍等待固定时间后继续（允许降级解析）。
    """
    for sel in _NOTE_READY_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=5_000)
            logger.debug("详情页内容就绪（选择器：%s）", sel)
            break
        except PlaywrightTimeoutError:
            continue
    else:
        logger.debug("详情页未检测到已知选择器，等待 %.1f 秒后继续", _RENDER_WAIT)

    # 额外等待确保 JS 渲染完成（互动数据、评论区等）
    await asyncio.sleep(_RENDER_WAIT)
