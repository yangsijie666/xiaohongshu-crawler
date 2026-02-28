"""
评论采集模块

职责：
  - 在笔记详情页定位评论区域
  - 滚动评论区加载更多评论（若不足目标条数）
  - 按顺序提取评论 DOM 元素，调用 parser 解析
  - 返回结构化评论列表

采集流程：
  1. 在已加载的笔记详情页中定位评论区
  2. 滚动评论区加载更多（若不足目标条数）
  3. 提取评论元素并逐条解析
  4. 返回最多 max_count 条评论

用法：
    comments = await fetch_comments(page, note_id="abc123", max_count=20)
"""

from __future__ import annotations

import asyncio
import logging
import random

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.parser import parse_comment

logger = logging.getLogger(__name__)

# 单条评论选择器（按优先级尝试）
# 真实 DOM：.comments-container > .parent-comment > .comment-item#comment-{id}
# 使用 .parent-comment > .comment-item 仅选取主评论，排除 .comment-item-sub 子回复
_COMMENT_ITEM_SELECTORS = [
    ".parent-comment > .comment-item",         # 精确：仅主评论
    ".comments-container .comment-item",        # 降级：含子回复
    ".comment-item",                            # 通用降级
]

# 等待评论区出现的超时（毫秒）
_COMMENT_WAIT_TIMEOUT_MS = 10_000

# 滚动评论区时的参数
_SCROLL_PX_MIN = 200
_SCROLL_PX_MAX = 400
_MAX_STALE_ROUNDS = 3


async def fetch_comments(
    page: Page,
    note_id: str,
    max_count: int = 20,
    scroll_pause: float = 1.5,
    scroll_interval: tuple[float, float] = (1.0, 2.0),
) -> list[dict]:
    """在笔记详情页中采集评论列表。

    要求页面已加载笔记详情，不会自行导航。

    Args:
        page: 已加载笔记详情页的 Playwright Page 对象
        note_id: 笔记 ID（附加到每条评论数据中）
        max_count: 最多采集评论条数
        scroll_pause: 每次滚动后固定等待时间（秒）
        scroll_interval: 额外随机延迟范围 (min, max)（秒）

    Returns:
        评论字典列表，每条包含：
        comment_id / note_id / user_name / user_id / content / likes / time / ip_location
    """
    logger.info("开始采集评论（note_id=%s，目标条数=%d）", note_id, max_count)

    # 检测评论元素选择器
    item_selector = await _detect_comment_selector(page)
    if item_selector is None:
        logger.warning("未找到评论元素（note_id=%s），可能无评论或选择器失效", note_id)
        return []

    logger.info("评论选择器确认：%s", item_selector)

    # 滚动加载更多评论
    await _scroll_comments(
        page,
        item_selector=item_selector,
        target_count=max_count,
        scroll_pause=scroll_pause,
        scroll_interval=scroll_interval,
    )

    # 提取并解析评论
    comment_els = await page.query_selector_all(item_selector)
    logger.info("共获取到 %d 个评论元素，开始解析...", len(comment_els))

    results: list[dict] = []
    for i, el in enumerate(comment_els[:max_count]):
        parsed = await parse_comment(el, note_id)
        if parsed:
            results.append(parsed)
        else:
            logger.debug("评论 #%d 解析失败，已跳过", i + 1)

    logger.info(
        "评论采集完成：note_id=%s，成功解析 %d/%d 条",
        note_id,
        len(results),
        min(len(comment_els), max_count),
    )
    return results


async def _detect_comment_selector(page: Page) -> str | None:
    """按优先级尝试多个候选选择器，返回第一个有匹配元素的。

    等待最长 10 秒，等不到则返回 None（笔记可能无评论）。
    """
    for sel in _COMMENT_ITEM_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=_COMMENT_WAIT_TIMEOUT_MS)
            count = len(await page.query_selector_all(sel))
            if count > 0:
                logger.debug("评论选择器 '%s' 命中 %d 个元素", sel, count)
                return sel
        except PlaywrightTimeoutError:
            logger.debug("评论选择器 '%s' 超时，尝试下一个", sel)
        except Exception as e:
            logger.debug("评论选择器 '%s' 异常：%s", sel, e)

    return None


async def _scroll_comments(
    page: Page,
    item_selector: str,
    target_count: int,
    scroll_pause: float,
    scroll_interval: tuple[float, float],
) -> None:
    """滚动评论区容器以加载更多评论。

    小红书笔记详情页的评论区位于 .note-scroller 可滚动容器内。
    需要对该容器进行滚动，而非页面级滚动。
    若找不到 .note-scroller 则回退到页面级滚动。
    """
    stale_rounds = 0

    # 评论区所在的可滚动容器
    scroller_selectors = [".note-scroller", ".interaction-container"]

    while True:
        current_count = len(await page.query_selector_all(item_selector))
        logger.debug("当前评论数：%d / 目标：%d", current_count, target_count)

        if current_count >= target_count:
            logger.info("已达到目标评论数（%d），停止滚动", target_count)
            break

        # 对可滚动容器执行滚动
        scroll_px = random.randint(_SCROLL_PX_MIN, _SCROLL_PX_MAX)
        scrolled = False
        for sel in scroller_selectors:
            scroller = await page.query_selector(sel)
            if scroller:
                await scroller.evaluate(f"el => el.scrollBy(0, {scroll_px})")
                scrolled = True
                break
        if not scrolled:
            # 回退到页面级滚动
            await page.mouse.wheel(0, scroll_px)

        # 等待新评论加载
        await asyncio.sleep(scroll_pause)
        extra_wait = random.uniform(*scroll_interval)
        await asyncio.sleep(extra_wait)

        new_count = len(await page.query_selector_all(item_selector))

        if new_count <= current_count:
            stale_rounds += 1
            logger.debug("评论数未增加，stale_rounds=%d", stale_rounds)
            if stale_rounds >= _MAX_STALE_ROUNDS:
                logger.info("连续 %d 轮无新增评论，停止滚动", stale_rounds)
                break
        else:
            stale_rounds = 0
