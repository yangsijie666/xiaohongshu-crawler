"""
CrawlerSession Phase B 方法测试

测试 B1/B3 后端：search_notes 和 get_note_detail 方法

测试策略：
  - BrowserManager 和 src 模块均 mock，不依赖真实浏览器
  - 覆盖：浏览器未运行时的错误返回、正常调用路径、参数透传
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.session import CrawlerSession


class TestCrawlerSessionSearchNotes:
    """测试 CrawlerSession.search_notes() 方法。"""

    async def test_returns_error_dict_when_not_running(self):
        """浏览器未启动时应返回含 error=True 的字典，不抛出异常。"""
        session = CrawlerSession()
        result = await session.search_notes("测试关键词")

        assert isinstance(result, dict)
        assert result.get("error") is True
        assert "message" in result

    async def test_calls_search_module_with_correct_args(self):
        """应将 keyword 和 max_count 正确传入 src.search.search_notes。"""
        mock_results = [{"note_id": "1", "title": "笔记一"}, {"note_id": "2", "title": "笔记二"}]

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=mock_results)) as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()
                result = await session.search_notes("Python", max_count=10)

                mock_search.assert_called_once_with(mock_bm, keyword="Python", max_count=10)
                assert result["keyword"] == "Python"
                assert result["count"] == 2
                assert result["results"] == mock_results

    async def test_returns_structured_response_keys(self):
        """返回值必须包含 keyword / count / results 三个键。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])):
                # Phase D: 空结果时会检测登录态，mock 为已登录以获得正常空响应
                with patch("src.session.is_logged_in", new=AsyncMock(return_value=True)):
                    mock_bm = AsyncMock()
                    MockBM.return_value = mock_bm
                    mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                    mock_bm.__aexit__ = AsyncMock(return_value=None)
                    mock_bm.new_page = AsyncMock(return_value=AsyncMock())

                    session = CrawlerSession()
                    await session.start()
                    result = await session.search_notes("keyword")

                    assert "keyword" in result
                    assert "count" in result
                    assert "results" in result

    async def test_uses_browser_lock_during_search(self):
        """搜索期间应持有 browser lock（通过 _lock 串行化）。"""
        lock_acquired_during_search = False

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes") as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()

                async def check_lock(*args, **kwargs):
                    nonlocal lock_acquired_during_search
                    # 尝试立即获取锁（应该失败，因为 search_notes 持有锁）
                    lock_acquired_during_search = session._lock.locked()
                    return []

                mock_search.side_effect = check_lock

                await session.search_notes("test")
                assert lock_acquired_during_search is True

    async def test_default_max_count_is_20(self):
        """默认 max_count 应为 20。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])) as mock_search:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()
                await session.search_notes("test")

                call_kwargs = mock_search.call_args[1]
                assert call_kwargs["max_count"] == 20


class TestCrawlerSessionSearchNotesRaceCondition:
    """测试 search_notes 的竞态条件二次防护路径。"""

    async def test_returns_error_when_bm_is_none_despite_running_flag(self):
        """_running=True 但 _bm=None 时（stop() 竞态），应返回 error dict。

        Phase D: _ensure_browser() 会尝试自动恢复，需 mock BrowserManager
        使恢复也失败，验证最终返回 BROWSER_CRASHED 错误。
        """
        with patch("src.session.BrowserManager") as MockBM:
            # 恢复也失败
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(side_effect=RuntimeError("恢复失败"))
            mock_bm.__aexit__ = AsyncMock(return_value=None)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            session._running = True  # 绕过快速路径
            session._bm = None       # 模拟 stop() 已将 _bm 置空

            result = await session.search_notes("test")

            assert isinstance(result, dict)
            assert result.get("error") is True
            assert result.get("code") == "BROWSER_CRASHED"


class TestCrawlerSessionGetNoteDetailRaceCondition:
    """测试 get_note_detail 的竞态条件二次防护路径。"""

    async def test_returns_error_when_bm_is_none_despite_running_flag(self):
        """_running=True 但 _bm=None 时（stop() 竞态），应返回 error dict。"""
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(side_effect=RuntimeError("恢复失败"))
            mock_bm.__aexit__ = AsyncMock(return_value=None)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            session._running = True
            session._bm = None

            result = await session.get_note_detail("https://www.xiaohongshu.com/explore/abc123")

            assert isinstance(result, dict)
            assert result.get("error") is True
            assert result.get("code") == "BROWSER_CRASHED"


class TestCrawlerSessionGetNoteDetail:
    """测试 CrawlerSession.get_note_detail() 方法。"""

    async def test_returns_error_dict_when_not_running(self):
        """浏览器未启动时应返回含 error=True 的字典，不抛出异常。"""
        session = CrawlerSession()
        result = await session.get_note_detail("https://www.xiaohongshu.com/explore/abc123")

        assert isinstance(result, dict)
        assert result.get("error") is True
        assert "message" in result

    async def test_calls_fetch_single_note_with_correct_args(self):
        """应将 note_url 和 max_comments 正确传入 src.note.fetch_single_note。"""
        mock_detail = {"note_id": "abc123", "title": "测试笔记", "comments": []}
        note_url = "https://www.xiaohongshu.com/explore/abc123?xsec_token=xyz"

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value=mock_detail)) as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()
                result = await session.get_note_detail(note_url, max_comments=5)

                mock_fetch.assert_called_once_with(mock_bm, note_url=note_url, max_comments=5)
                assert result == mock_detail

    async def test_returns_error_dict_when_fetch_returns_none(self):
        """fetch_single_note 返回 None 时应包装为 error dict，而非透传 None。"""
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value=None)):
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()
                result = await session.get_note_detail(note_url)

                assert isinstance(result, dict)
                assert result.get("error") is True
                assert "message" in result

    async def test_default_max_comments_is_20(self):
        """默认 max_comments 应为 20。"""
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note", new=AsyncMock(return_value={})) as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()
                await session.get_note_detail(note_url)

                call_kwargs = mock_fetch.call_args[1]
                assert call_kwargs["max_comments"] == 20

    async def test_uses_browser_lock_during_fetch(self):
        """采集笔记期间应持有 browser lock。"""
        lock_acquired = False
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.note.fetch_single_note") as mock_fetch:
                mock_bm = AsyncMock()
                MockBM.return_value = mock_bm
                mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
                mock_bm.__aexit__ = AsyncMock(return_value=None)

                session = CrawlerSession()
                await session.start()

                async def check_lock(*args, **kwargs):
                    nonlocal lock_acquired
                    lock_acquired = session._lock.locked()
                    return {}

                mock_fetch.side_effect = check_lock
                await session.get_note_detail(note_url)
                assert lock_acquired is True
