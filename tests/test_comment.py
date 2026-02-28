"""
comment 模块单元测试

测试策略：
  - Playwright Page 全部使用 AsyncMock 模拟，不依赖真实浏览器
  - asyncio.sleep 打补丁为 no-op，避免测试延迟
  - parse_comment 打补丁隔离 parser 依赖
  - 覆盖：fetch_comments、_detect_comment_selector、_scroll_comments
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

from src.comment import _detect_comment_selector, _scroll_comments, fetch_comments


# ============================================================
# 辅助函数
# ============================================================


def _make_page(
    selector_elements: dict | None = None,
    all_elements: dict | None = None,
) -> AsyncMock:
    """创建通用模拟 Page。

    Args:
        selector_elements: sel → element 的映射（query_selector）
        all_elements: sel → [element, ...] 的映射（query_selector_all）
    """
    page = AsyncMock()
    selector_elements = selector_elements or {}
    all_elements = all_elements or {}

    async def wait_for_selector(sel, *, timeout=None):
        if sel not in (all_elements or {}) or not all_elements.get(sel):
            raise PlaywrightTimeoutError("timeout")

    page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
    page.query_selector_all = AsyncMock(
        side_effect=lambda sel: all_elements.get(sel, [])
    )
    page.query_selector = AsyncMock(
        side_effect=lambda sel: selector_elements.get(sel)
    )
    page.mouse = AsyncMock()
    page.mouse.wheel = AsyncMock()
    return page


# ============================================================
# _detect_comment_selector
# ============================================================


class TestDetectCommentSelector:
    """测试评论选择器检测逻辑。"""

    async def test_returns_first_matching_selector(self):
        """第一个有元素的选择器应被返回。"""
        el = AsyncMock()
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(return_value=None)
        page.query_selector_all = AsyncMock(return_value=[el])

        result = await _detect_comment_selector(page)

        assert result is not None
        assert isinstance(result, str)

    async def test_skips_empty_selector(self):
        """有匹配元素的才返回（空列表跳过，非空才命中）。"""
        el = AsyncMock()
        call_count = 0

        page = AsyncMock()

        async def wait_for_selector(sel, *, timeout=None):
            pass  # 不抛出

        async def qsa(sel):
            nonlocal call_count
            call_count += 1
            # 第一次调用返回空（跳过），第二次返回有元素
            return [] if call_count == 1 else [el]

        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
        page.query_selector_all = AsyncMock(side_effect=qsa)

        result = await _detect_comment_selector(page)

        assert result is not None
        assert call_count >= 2

    async def test_returns_none_when_all_selectors_timeout(self):
        """所有选择器超时时应返回 None。"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(
            side_effect=PlaywrightTimeoutError("timeout")
        )

        result = await _detect_comment_selector(page)

        assert result is None

    async def test_returns_none_on_exception(self):
        """选择器抛出非超时异常时应继续尝试并最终返回 None。"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(
            side_effect=Exception("unexpected")
        )

        result = await _detect_comment_selector(page)

        assert result is None


# ============================================================
# _scroll_comments
# ============================================================


class TestScrollComments:
    """测试评论区滚动逻辑。"""

    async def test_stops_immediately_when_count_met(self):
        """当前评论数已达目标时，不应执行滚动。"""
        el = AsyncMock()
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[el] * 5)
        page.query_selector = AsyncMock(return_value=None)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_comments(
                page,
                item_selector=".comment-item",
                target_count=3,  # target < current
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        page.mouse.wheel.assert_not_called()

    async def test_scrolls_using_scroller_element(self):
        """找到可滚动容器时应通过容器滚动而非 mouse.wheel。"""
        el = AsyncMock()
        scroller = AsyncMock()
        scroller.evaluate = AsyncMock()

        counts = [0, 5]  # 第一次 0，第二次 5 → 满足目标
        call_idx = 0

        async def qsa(sel):
            nonlocal call_idx
            if ".comment-item" in sel or sel == ".comment-item":
                val = counts[min(call_idx, len(counts) - 1)]
                call_idx += 1
                return [AsyncMock()] * val
            return []

        async def qs(sel):
            if sel in (".note-scroller", ".interaction-container"):
                return scroller if sel == ".note-scroller" else None
            return None

        page = AsyncMock()
        page.query_selector_all = AsyncMock(side_effect=qsa)
        page.query_selector = AsyncMock(side_effect=qs)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_comments(
                page,
                item_selector=".comment-item",
                target_count=5,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        scroller.evaluate.assert_called()
        page.mouse.wheel.assert_not_called()

    async def test_falls_back_to_mouse_wheel_when_no_scroller(self):
        """找不到滚动容器时应回退到 mouse.wheel 滚动。"""
        counts = [0, 5]
        call_idx = 0

        async def qsa(sel):
            nonlocal call_idx
            val = counts[min(call_idx, len(counts) - 1)]
            call_idx += 1
            return [AsyncMock()] * val

        page = AsyncMock()
        page.query_selector_all = AsyncMock(side_effect=qsa)
        page.query_selector = AsyncMock(return_value=None)  # 无滚动容器
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            await _scroll_comments(
                page,
                item_selector=".comment-item",
                target_count=5,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        page.mouse.wheel.assert_called()

    async def test_stops_after_stale_rounds(self):
        """连续无新增评论达到阈值时应停止滚动。"""
        page = AsyncMock()
        page.query_selector_all = AsyncMock(return_value=[])  # 始终为空
        page.query_selector = AsyncMock(return_value=None)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with patch("asyncio.sleep", new=AsyncMock()):
            # 目标 10 但始终为 0，应在 stale_rounds=3 后停止
            await _scroll_comments(
                page,
                item_selector=".comment-item",
                target_count=10,
                scroll_pause=0.0,
                scroll_interval=(0.0, 0.0),
            )

        # 至少进行了滚动（不会无限循环）
        assert page.mouse.wheel.call_count >= 1


# ============================================================
# fetch_comments
# ============================================================


class TestFetchComments:
    """测试 fetch_comments 公共接口。"""

    async def test_returns_empty_when_no_selector_found(self):
        """未找到评论选择器时应返回空列表。"""
        page = AsyncMock()
        page.wait_for_selector = AsyncMock(
            side_effect=PlaywrightTimeoutError("timeout")
        )

        result = await fetch_comments(page, note_id="abc", max_count=5)

        assert result == []

    async def test_returns_parsed_comments(self):
        """成功解析时应返回评论列表。"""
        el1 = AsyncMock()
        el2 = AsyncMock()
        mock_comment1 = {"comment_id": "c1", "content": "评论1"}
        mock_comment2 = {"comment_id": "c2", "content": "评论2"}

        page = AsyncMock()

        async def wait_for_selector(sel, *, timeout=None):
            pass  # 不超时

        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
        page.query_selector_all = AsyncMock(return_value=[el1, el2])
        page.query_selector = AsyncMock(return_value=None)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with (
            patch("src.comment.parse_comment", side_effect=[mock_comment1, mock_comment2]),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await fetch_comments(page, note_id="abc", max_count=10)

        assert len(result) == 2
        assert result[0]["comment_id"] == "c1"

    async def test_skips_failed_comments(self):
        """解析返回 None 的评论应被跳过。"""
        el = AsyncMock()
        page = AsyncMock()

        async def wait_for_selector(sel, *, timeout=None):
            pass

        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
        page.query_selector_all = AsyncMock(return_value=[el])
        page.query_selector = AsyncMock(return_value=None)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        with (
            patch("src.comment.parse_comment", return_value=None),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await fetch_comments(page, note_id="abc", max_count=5)

        assert result == []

    async def test_respects_max_count(self):
        """最多返回 max_count 条评论。"""
        els = [AsyncMock() for _ in range(10)]
        page = AsyncMock()

        async def wait_for_selector(sel, *, timeout=None):
            pass

        page.wait_for_selector = AsyncMock(side_effect=wait_for_selector)
        page.query_selector_all = AsyncMock(return_value=els)
        page.query_selector = AsyncMock(return_value=None)
        page.mouse = AsyncMock()
        page.mouse.wheel = AsyncMock()

        def fake_parse(el, note_id):
            return {"comment_id": "x", "content": "c"}

        with (
            patch("src.comment.parse_comment", side_effect=fake_parse),
            patch("asyncio.sleep", new=AsyncMock()),
        ):
            result = await fetch_comments(page, note_id="abc", max_count=3)

        assert len(result) == 3
