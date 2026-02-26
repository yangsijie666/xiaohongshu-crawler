"""
搜索结果采集模块

职责：
  - 按关键词导航到小红书搜索页
  - 模拟人类滚动行为触发瀑布流加载
  - 提取页面上的笔记卡片，调用 parser 解析
  - 达到目标条数或无新内容时停止

翻页策略（瀑布流）：
  小红书搜索结果为无限滚动（非分页），通过监测卡片数量变化判断是否还有新内容。
  连续两次滚动后卡片数未增加，则认为已到达底部。

用法：
    async with BrowserManager() as bm:
        results = await search_notes(bm, keyword="Python", max_count=20)
"""

from __future__ import annotations

import asyncio
import logging
import random
from urllib.parse import quote

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.browser import BrowserManager
from src.parser import parse_search_card

logger = logging.getLogger(__name__)

# 搜索页 URL 模板（type=51 为综合搜索）
_SEARCH_URL = "https://www.xiaohongshu.com/search_result?keyword={keyword}&type=51"

# 搜索卡片选择器（按优先级尝试）
_CARD_SELECTORS = [
    "section.note-item",
    "div.note-item",
    "[class*='NoteItem']",
    ".search-result-list > *",  # 降级：容器直接子元素
]

# 等待第一批卡片超时（毫秒）
_INITIAL_WAIT_TIMEOUT_MS = 30_000

# 单次滚动距离范围（像素）
_SCROLL_PX_MIN = 300
_SCROLL_PX_MAX = 600

# 连续无新增卡片次数阈值，达到则停止滚动
_MAX_STALE_ROUNDS = 2


async def search_notes(
    bm: BrowserManager,
    keyword: str,
    max_count: int = 20,
    scroll_pause: float = 1.5,
    scroll_interval: tuple[float, float] = (1.0, 3.0),
) -> list[dict]:
    """按关键词搜索小红书，采集笔记摘要列表。

    Args:
        bm: 已初始化且登录的 BrowserManager 实例
        keyword: 搜索关键词
        max_count: 最多返回的笔记条数
        scroll_pause: 每次滚动后的固定等待时间（秒）
        scroll_interval: 额外随机延迟范围 (min, max)（秒）

    Returns:
        包含笔记摘要字典的列表，每条包含：
        note_id / title / author / author_id / cover_url / likes / note_url / note_type
    """
    url = _SEARCH_URL.format(keyword=quote(keyword))
    logger.info("开始搜索：keyword=%s，目标条数=%d", keyword, max_count)

    page = await bm.new_page()
    try:
        # 导航到搜索页
        await page.goto(url, wait_until="domcontentloaded", timeout=_INITIAL_WAIT_TIMEOUT_MS)
        logger.info("搜索页已加载：%s", url)

        # 等待第一批卡片出现
        card_selector = await _detect_card_selector(page)
        if card_selector is None:
            logger.error("未找到搜索结果卡片，请检查选择器或登录状态（keyword=%s）", keyword)
            return []

        logger.info("卡片选择器确认：%s", card_selector)

        # 滚动加载更多卡片
        await _scroll_to_load(
            page,
            card_selector=card_selector,
            target_count=max_count,
            scroll_pause=scroll_pause,
            scroll_interval=scroll_interval,
        )

        # 提取所有卡片元素并解析
        cards = await page.query_selector_all(card_selector)
        logger.info("共获取到 %d 个卡片元素，开始解析...", len(cards))

        results: list[dict] = []
        for i, card in enumerate(cards[:max_count]):
            parsed = await parse_search_card(card)
            if parsed:
                results.append(parsed)
            else:
                logger.debug("卡片 #%d 解析失败，已跳过", i + 1)

        logger.info(
            "搜索采集完成：keyword=%s，成功解析 %d/%d 条",
            keyword,
            len(results),
            len(cards[:max_count]),
        )
        return results

    except PlaywrightTimeoutError:
        logger.error("搜索页加载超时（keyword=%s）", keyword)
        return []
    except Exception as e:
        logger.error("搜索采集异常：%s", e, exc_info=True)
        return []
    finally:
        await page.close()


async def _detect_card_selector(page) -> str | None:
    """尝试多个候选选择器，返回第一个在页面中有匹配元素的选择器。

    等待最长 30 秒等待第一批卡片出现。

    Args:
        page: Playwright Page 对象

    Returns:
        有效的 CSS 选择器字符串，或 None（全部失败）
    """
    for sel in _CARD_SELECTORS:
        try:
            await page.wait_for_selector(sel, timeout=_INITIAL_WAIT_TIMEOUT_MS)
            count = len(await page.query_selector_all(sel))
            if count > 0:
                logger.debug("选择器 '%s' 命中 %d 个元素", sel, count)
                return sel
        except PlaywrightTimeoutError:
            logger.debug("选择器 '%s' 超时，尝试下一个", sel)
        except Exception as e:
            logger.debug("选择器 '%s' 失败：%s", sel, e)

    return None


async def _scroll_to_load(
    page,
    card_selector: str,
    target_count: int,
    scroll_pause: float,
    scroll_interval: tuple[float, float],
) -> None:
    """循环滚动页面直到达到目标卡片数或无新内容。

    Args:
        page: Playwright Page 对象
        card_selector: 已验证的卡片 CSS 选择器
        target_count: 目标卡片数量
        scroll_pause: 固定等待时间（秒）
        scroll_interval: 额外随机等待范围 (min, max)（秒）
    """
    stale_rounds = 0  # 连续无新增轮次

    while True:
        current_count = len(await page.query_selector_all(card_selector))
        logger.debug("当前卡片数：%d / 目标：%d", current_count, target_count)

        if current_count >= target_count:
            logger.info("已达到目标卡片数（%d），停止滚动", target_count)
            break

        # 执行随机滚动
        scroll_px = random.randint(_SCROLL_PX_MIN, _SCROLL_PX_MAX)
        await page.mouse.wheel(0, scroll_px)

        # 等待新内容加载
        await asyncio.sleep(scroll_pause)
        extra_wait = random.uniform(*scroll_interval)
        await asyncio.sleep(extra_wait)

        new_count = len(await page.query_selector_all(card_selector))

        if new_count <= current_count:
            stale_rounds += 1
            logger.debug("卡片数未增加，stale_rounds=%d", stale_rounds)
            if stale_rounds >= _MAX_STALE_ROUNDS:
                logger.info("连续 %d 轮无新增卡片，判断已到达底部", stale_rounds)
                break
        else:
            stale_rounds = 0  # 有新增，重置计数
