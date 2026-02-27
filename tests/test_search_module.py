"""
search 模块单元测试

测试策略：
  - BrowserManager 使用 AsyncMock 模拟，不依赖真实浏览器
  - asyncio.sleep 打补丁为 no-op，避免测试延迟
  - parse_search_card 打补丁隔离 parser 依赖
  - 覆盖：search_notes、_detect_card_selector、_scroll_to_load
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.search import _detect_card_selector, _scroll_to_load, search_notes


# ============================================================
# 辅助函数
# ============================================================


def _make_bm(page: AsyncMock | None = None) -> AsyncMock:
    """创建模拟 BrowserManager，new_page() 返回指定的 page mock。"""
    bm = AsyncMock()
    bm.new_page = AsyncMock(return_value=page or AsyncMock())
    return bm


def _make_page(
    qsa_results: dict | None = None,
    goto_raises: Exception | None = None,
) -> AsyncMock:
    """创建通用模拟 Page。

    Args:
        qsa_results: sel → [element, ...] 的映射
        goto_raises: 若设置，goto() 会抛出该异常
    """
    page = AsyncMock()
    qsa_results = qsa_results or {}

    if goto_raises:
        page.goto = AsyncMock(side_effect=goto_raises)
    else:
        page.goto = AsyncMock(return_value=None)

    page.query_selector_all = AsyncMock(
        side_effect=lambda sel: qsa_results.get(sel, [])
    )
    page.wait_for_selector = AsyncMock(
        side_effect=lambda sel, **kw: (_ for _ in ()).throw(PlaywrightTimeoutError("timeout"))
        if not qsa_results.get(sel)
        else None
    )
    page.mouse = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.close = AsyncMock()
    return page


# ============================================================
# _detect_card_selector
# ============================================================


class TestDetectCardSelector:
    """测试搜索卡片选择器检测。"""

    async def test_returns_selector_with_elements(self):
        """有元素的选择器应被返回。"""
        el = AsyncMock()
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=[el])

        result = await _detect_card_selector(page)

        assert result is not None

    async def test_returns_none_when_all_timeout(self):
        """所有选择器超时时应返回 None。"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(
            side_effect=PlaywrightTimeoutError("timeout")
        )

        result = await _detect_card_selector(page)

        assert result is None

    async def test_returns_none_on_exception(self):
        """选择器抛出异常时应继续尝试并最终返回 None。"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(side_effect=Exception("unexpected"))

        result = await _detect_card_selector(page)

        assert result is None

    async def test_skips_selector_with_zero_elements(self):
        """有匹配元素（非空）才返回，空列表跳过。"""
        el = AsyncMock()
        call_count = 0

        async def qsa(sel):
            nonlocal call_count
            call_count += 1
            return [] if call_count == 1 else [el]

        page = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(side_effect=qsa)

        result = await _detect_card_selector(page)

        assert result is not None
        assert call_count >= 2


# ============================================================
# _scroll_to_load
# ============================================================


class TestScrollToLoad:
    """测试瀑布流加载滚动逻辑。"""

    async def test_stops_immediately_when_count_met(self):
        """当前卡片数已达目标时不执行滚动。"""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[AsyncMock()] * 5)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_to_load(
                page,
                card_selector="section.note-item",
                target_count=3,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        page.mouse.wheel.assert_not_called()

    async def test_stops_after_stale_rounds(self):
        """连续无新增卡片达到阈值时停止。"""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_to_load(
                page,
                card_selector="section.note-item",
                target_count=20,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert page.mouse.wheel.call_count >= 1

    async def test_resets_stale_count_when_new_cards_appear(self):
        """出现新卡片时 stale_rounds 应重置。"""
        counts = [0, 3, 3, 3]  # 第二轮有增长，之后停滞
        call_idx = 0

        async def qsa(sel):
            nonlocal call_idx
            val = counts[min(call_idx, len(counts) - 1)]
            call_idx += 1
            return [AsyncMock()] * val

        page = AsyncMock()
        page.query_selector_all = AsyncMock(side_effect=qsa)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_to_load(
                page,
                card_selector="section.note-item",
                target_count=20,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert page.mouse.wheel.call_count >= 1


# ============================================================
# search_notes
# ============================================================


class TestSearchNotes:
    """测试 search_notes 公共接口。"""

    async def test_returns_empty_when_no_selector_found(self):
        """找不到卡片选择器时应返回空列表。"""
        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(
            side_effect=PlaywrightTimeoutError("timeout")
        )
        page.close = AsyncMock()

        bm = _make_bm(page)

        with patch("asyncio.sleep", new=AsyncMock()):
            result = await search_notes(
                bm,
                keyword="Python",
                max_count=5,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert result == []

    async def test_returns_parsed_cards(self):
        """找到卡片并成功解析时应返回结果列表。"""
        el = AsyncMock()
        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=[el, el])
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.close = AsyncMock()

        bm = _make_bm(page)

        mock_card = {"note_id": "n1", "title": "测试"}

        with (
            patch("src.search.parse_search_card", return_value=mock_card),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await search_notes(
                bm,
                keyword="Python",
                max_count=10,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert len(result) == 2

    async def test_skips_failed_cards(self):
        """parse_search_card 返回 None 的卡片应被跳过。"""
        el = AsyncMock()
        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=[el])
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.close = AsyncMock()

        bm = _make_bm(page)

        with (
            patch("src.search.parse_search_card", return_value=None),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await search_notes(
                bm,
                keyword="Python",
                max_count=5,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert result == []

    async def test_returns_empty_on_timeout(self):
        """页面加载超时时应返回空列表。"""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=PlaywrightTimeoutError("timeout"))
        page.close = AsyncMock()

        bm = _make_bm(page)

        result = await search_notes(bm, keyword="Python", max_count=5)

        assert result == []

    async def test_returns_empty_on_general_exception(self):
        """其他异常时应返回空列表。"""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("network error"))
        page.close = AsyncMock()

        bm = _make_bm(page)

        result = await search_notes(bm, keyword="Python", max_count=5)

        assert result == []

    async def test_closes_page_even_on_error(self):
        """无论成功或失败，page.close() 都应被调用。"""
        page = AsyncMock()
        page.goto = AsyncMock(side_effect=Exception("error"))
        page.close = AsyncMock()

        bm = _make_bm(page)

        await search_notes(bm, keyword="Python", max_count=5)

        page.close.assert_called_once()

    async def test_respects_max_count(self):
        """最多返回 max_count 条结果。"""
        els = [AsyncMock() for _ in range(10)]
        page = AsyncMock()
        page.goto = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=els)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()
        page.close = AsyncMock()

        bm = _make_bm(page)

        mock_card = {"note_id": "n1", "title": "测试"}

        with (
            patch("src.search.parse_search_card", return_value=mock_card),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await search_notes(
                bm,
                keyword="Python",
                max_count=3,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        assert len(result) == 3
