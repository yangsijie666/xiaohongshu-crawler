"""
CrawlerSession Phase C 方法测试

测试 crawl_keyword 和 get_saved_data 方法

测试策略：
  - BrowserManager 和 src 模块均 mock，不依赖真实浏览器
  - get_saved_data 使用 tmp_path fixture 测试文件系统操作
  - 覆盖：正常路径、浏览器未启动错误、参数边界、竞态条件
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.session import CrawlerSession


def _make_mock_bm():
    """创建支持 async with 协议的 Mock BrowserManager。"""
    mock_bm = AsyncMock()
    mock_bm.__aenter__ = AsyncMock(return_value=mock_bm)
    mock_bm.__aexit__ = AsyncMock(return_value=None)
    return mock_bm


# ============================================================
# CrawlerSession.crawl_keyword() 测试
# ============================================================


class TestCrawlerSessionCrawlKeyword:
    """测试 CrawlerSession.crawl_keyword() 方法。"""

    async def test_returns_error_when_not_running(self):
        """浏览器未启动时应返回含 error=True 的字典，不抛出异常。"""
        session = CrawlerSession()
        result = await session.crawl_keyword("测试")

        assert isinstance(result, dict)
        assert result.get("error") is True
        assert "message" in result

    async def test_calls_search_and_fetch_details(self):
        """应按顺序调用 search_notes 和 fetch_note_details，参数正确传递。"""
        mock_search_results = [
            {"note_id": "1", "title": "笔记一", "note_url": "https://example.com/1"},
        ]
        mock_note_details = [
            {"note_id": "1", "title": "笔记一", "comments": []},
        ]

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=mock_search_results)) as mock_search:
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=mock_note_details)) as mock_fetch:
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()
                        await session.crawl_keyword("测试关键词", max_notes=1, max_comments=5)

                        mock_search.assert_called_once()
                        assert mock_search.call_args[1]["keyword"] == "测试关键词"
                        assert mock_search.call_args[1]["max_count"] == 1
                        mock_fetch.assert_called_once()
                        assert mock_fetch.call_args[1]["max_comments"] == 5

    async def test_returns_structured_result(self):
        """返回值应包含 keyword/search_count/detail_count/total_comments/summary 键。"""
        mock_search_results = [{"note_id": "1"}, {"note_id": "2"}]
        mock_note_details = [
            {"note_id": "1", "comments": [{"id": "c1"}, {"id": "c2"}]},
            {"note_id": "2", "comments": [{"id": "c3"}]},
        ]

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=mock_search_results)):
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=mock_note_details)):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()
                        result = await session.crawl_keyword("测试")

                        assert result["keyword"] == "测试"
                        assert result["search_count"] == 2
                        assert result["detail_count"] == 2
                        assert result["total_comments"] == 3
                        assert "summary" in result

    async def test_limits_max_notes_to_20(self):
        """max_notes 超过 20 时，传给 search_notes 的 max_count 应截断到 20。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])) as mock_search:
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=[])):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()
                        await session.crawl_keyword("test", max_notes=50)

                        call_kwargs = mock_search.call_args[1]
                        assert call_kwargs["max_count"] == 20

    async def test_handles_empty_search_results(self):
        """搜索无结果时应返回有效的空结构（非 error），不崩溃。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])):
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=[])):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()
                        result = await session.crawl_keyword("无结果关键词")

                        assert result.get("error") is not True
                        assert result["search_count"] == 0
                        assert result["detail_count"] == 0
                        assert result["total_comments"] == 0

    async def test_saves_data_via_storage(self):
        """应调用 Storage.save_all 持久化数据，参数为关键词 + 两个列表。"""
        mock_search_results = [{"note_id": "1"}]
        mock_note_details = [{"note_id": "1", "comments": []}]

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=mock_search_results)):
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=mock_note_details)):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        mock_storage = MagicMock()
                        MockStorage.return_value = mock_storage

                        session = CrawlerSession()
                        await session.start()
                        await session.crawl_keyword("保存测试")

                        mock_storage.save_all.assert_called_once_with(
                            "保存测试", mock_search_results, mock_note_details
                        )

    async def test_uses_browser_lock_during_crawl(self):
        """采集期间应持有 browser lock（保证串行化）。"""
        lock_acquired = False

        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes") as mock_search:
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=[])):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()

                        async def check_lock(*args, **kwargs):
                            nonlocal lock_acquired
                            lock_acquired = session._lock.locked()
                            return []

                        mock_search.side_effect = check_lock
                        await session.crawl_keyword("lock_test")

                        assert lock_acquired is True

    async def test_returns_error_when_bm_none_race_condition(self):
        """_running=True 但 _bm=None（竞态），应返回 error dict。

        Phase D: _ensure_browser() 会尝试自动恢复，mock 使恢复失败。
        """
        with patch("src.session.BrowserManager") as MockBM:
            mock_bm = AsyncMock()
            mock_bm.__aenter__ = AsyncMock(side_effect=RuntimeError("恢复失败"))
            mock_bm.__aexit__ = AsyncMock(return_value=None)
            MockBM.return_value = mock_bm

            session = CrawlerSession()
            session._running = True
            session._bm = None

            result = await session.crawl_keyword("test")

            assert isinstance(result, dict)
            assert result.get("error") is True
            assert result.get("code") == "BROWSER_CRASHED"

    async def test_default_max_notes_is_10(self):
        """默认 max_notes 应为 10。"""
        with patch("src.session.BrowserManager") as MockBM:
            with patch("src.search.search_notes", new=AsyncMock(return_value=[])) as mock_search:
                with patch("src.note.fetch_note_details", new=AsyncMock(return_value=[])):
                    with patch("src.session.Storage") as MockStorage:
                        mock_bm = _make_mock_bm()
                        MockBM.return_value = mock_bm
                        MockStorage.return_value = MagicMock()

                        session = CrawlerSession()
                        await session.start()
                        await session.crawl_keyword("test")

                        call_kwargs = mock_search.call_args[1]
                        assert call_kwargs["max_count"] == 10


# ============================================================
# CrawlerSession.get_saved_data() 测试
# ============================================================


class TestCrawlerSessionGetSavedData:
    """测试 CrawlerSession.get_saved_data() 方法。"""

    async def test_returns_empty_when_data_dir_not_exists(self, tmp_path):
        """data 目录不存在时应返回空文件列表，不抛出异常。"""
        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path / "nonexistent")

        assert isinstance(result, dict)
        assert result["files"] == []

    async def test_returns_all_files_when_no_keyword_filter(self, tmp_path):
        """不传 keyword 时应返回所有可识别的数据文件。"""
        raw_dir = tmp_path / "raw"
        processed_dir = tmp_path / "processed"
        raw_dir.mkdir(parents=True)
        processed_dir.mkdir(parents=True)

        (raw_dir / "Python教程_20240315_143022.json").write_text("{}", encoding="utf-8")
        (raw_dir / "美食_20240315_143022.json").write_text("{}", encoding="utf-8")
        (processed_dir / "Python教程_20240315_143022.xlsx").write_bytes(b"xlsx_content")

        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path)

        assert len(result["files"]) == 3

    async def test_filters_files_by_keyword(self, tmp_path):
        """传入 keyword 时应只返回匹配的文件（不区分大小写，模糊匹配）。"""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        (raw_dir / "Python教程_20240315_143022.json").write_text("{}", encoding="utf-8")
        (raw_dir / "美食推荐_20240315_143022.json").write_text("{}", encoding="utf-8")

        session = CrawlerSession()
        result = await session.get_saved_data(keyword="python", data_dir=tmp_path)

        assert len(result["files"]) == 1
        assert "Python" in result["files"][0]["keyword"]

    async def test_returns_file_metadata(self, tmp_path):
        """每条文件记录应包含 path/keyword/created_at/size_bytes 四个字段。"""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        test_file = raw_dir / "测试关键词_20240315_143022.json"
        test_file.write_text('{"count": 5}', encoding="utf-8")

        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path)

        assert len(result["files"]) == 1
        file_info = result["files"][0]
        assert "path" in file_info
        assert "keyword" in file_info
        assert "created_at" in file_info
        assert "size_bytes" in file_info
        assert file_info["keyword"] == "测试关键词"
        assert file_info["size_bytes"] > 0

    async def test_extracts_keyword_from_notes_prefix(self, tmp_path):
        """notes_ 前缀的文件应正确去除前缀后提取 keyword。"""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        (raw_dir / "notes_小红书技巧_20240315_143022.json").write_text("{}", encoding="utf-8")

        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path)

        assert len(result["files"]) == 1
        assert result["files"][0]["keyword"] == "小红书技巧"

    async def test_ignores_unrecognized_files(self, tmp_path):
        """非数据文件（如 .gitkeep）应被忽略，不出现在结果中。"""
        raw_dir = tmp_path / "raw"
        raw_dir.mkdir(parents=True)
        (tmp_path / "processed").mkdir(parents=True)

        (raw_dir / ".gitkeep").write_text("", encoding="utf-8")
        (raw_dir / "关键词_20240315_143022.json").write_text("{}", encoding="utf-8")

        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path)

        assert len(result["files"]) == 1

    async def test_returns_files_key(self, tmp_path):
        """返回值必须包含 files 键。"""
        session = CrawlerSession()
        result = await session.get_saved_data(data_dir=tmp_path)

        assert "files" in result
        assert isinstance(result["files"], list)

    async def test_does_not_require_browser(self):
        """get_saved_data 不依赖浏览器，浏览器未启动时也可正常返回。"""
        session = CrawlerSession()
        # 浏览器未启动，data_dir 不存在
        result = await session.get_saved_data(data_dir=Path("/tmp/nonexistent_rednote_test_dir_xyz"))

        assert "files" in result
        assert result.get("error") is not True
