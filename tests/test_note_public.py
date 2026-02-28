"""
B2：fetch_single_note 公开接口测试

测试策略：
  - _extract_note_id_from_url 纯函数，直接测试
  - fetch_single_note 通过 mock _fetch_single_note 隔离浏览器调用
  - 覆盖：正常路径、无效 URL、None 降级、默认参数
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.note import _extract_note_id_from_url, fetch_single_note


class TestExtractNoteIdFromUrl:
    """测试从 URL 中提取 note_id 的工具函数。"""

    def test_extracts_id_from_standard_url(self):
        """标准 explore URL 应正确提取 note_id。"""
        url = "https://www.xiaohongshu.com/explore/65abc1234567890abcde?xsec_token=xxx"
        assert _extract_note_id_from_url(url) == "65abc1234567890abcde"

    def test_extracts_id_without_query_params(self):
        """不含查询参数的 URL 也应正确提取。"""
        url = "https://www.xiaohongshu.com/explore/abc123def456"
        assert _extract_note_id_from_url(url) == "abc123def456"

    def test_returns_none_for_url_without_explore(self):
        """不含 /explore/ 路径的 URL 应返回 None。"""
        assert _extract_note_id_from_url("https://www.xiaohongshu.com/search") is None

    def test_returns_none_for_empty_string(self):
        """空字符串应返回 None。"""
        assert _extract_note_id_from_url("") is None

    def test_returns_none_for_non_url(self):
        """非 URL 字符串应返回 None。"""
        assert _extract_note_id_from_url("not-a-url") is None

    def test_handles_mixed_case_note_id(self):
        """note_id 可能包含大小写字母和数字。"""
        url = "https://www.xiaohongshu.com/explore/AbC123XyZ"
        assert _extract_note_id_from_url(url) == "AbC123XyZ"


class TestFetchSingleNote:
    """测试 fetch_single_note 公开接口。"""

    async def test_returns_none_for_invalid_url(self):
        """URL 中无 note_id 时应返回 None，不抛出异常。"""
        mock_bm = MagicMock()
        result = await fetch_single_note(mock_bm, note_url="https://example.com/no/id")
        assert result is None

    async def test_returns_none_for_empty_url(self):
        """空 URL 应返回 None。"""
        mock_bm = MagicMock()
        result = await fetch_single_note(mock_bm, note_url="")
        assert result is None

    async def test_calls_internal_with_extracted_note_id(self):
        """应将从 URL 提取的 note_id 传入内部实现。"""
        mock_bm = MagicMock()
        mock_detail = {"note_id": "abc123", "title": "测试笔记", "comments": []}
        note_url = "https://www.xiaohongshu.com/explore/abc123?xsec_token=xyz"

        with patch("src.note._fetch_single_note", new=AsyncMock(return_value=mock_detail)) as mock_inner:
            result = await fetch_single_note(mock_bm, note_url=note_url, max_comments=10)

            mock_inner.assert_called_once()
            call_kwargs = mock_inner.call_args[1]
            assert call_kwargs["note_id"] == "abc123"
            assert call_kwargs["note_url"] == note_url
            assert call_kwargs["max_comments"] == 10
            assert result == mock_detail

    async def test_default_max_comments_is_20(self):
        """默认 max_comments 应为 20。"""
        mock_bm = MagicMock()
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.note._fetch_single_note", new=AsyncMock(return_value={})) as mock_inner:
            await fetch_single_note(mock_bm, note_url=note_url)
            assert mock_inner.call_args[1]["max_comments"] == 20

    async def test_returns_none_when_inner_returns_none(self):
        """内部函数返回 None 时应透传 None。"""
        mock_bm = MagicMock()
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.note._fetch_single_note", new=AsyncMock(return_value=None)):
            result = await fetch_single_note(mock_bm, note_url=note_url)
            assert result is None

    async def test_passes_bm_to_internal(self):
        """BrowserManager 实例应被正确传入内部函数。"""
        mock_bm = MagicMock()
        note_url = "https://www.xiaohongshu.com/explore/abc123"

        with patch("src.note._fetch_single_note", new=AsyncMock(return_value={})) as mock_inner:
            await fetch_single_note(mock_bm, note_url=note_url)
            # 第一个位置参数是 bm
            assert mock_inner.call_args[0][0] is mock_bm
