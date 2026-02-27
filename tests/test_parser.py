"""
parser 模块单元测试

测试策略：
  - normalize_count：同步纯函数，直接测试各种输入格式
  - 异步解析函数：使用 AsyncMock 模拟 Playwright ElementHandle / Page
    不依赖真实浏览器，完全在进程内运行
  - 覆盖：正常路径、降级路径（选择器未命中）、异常处理路径
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.parser import (
    _parse_interact_count,
    _query_text,
    normalize_count,
    parse_comment,
    parse_note_detail,
    parse_search_card,
)


# ============================================================
# normalize_count
# ============================================================


class TestNormalizeCount:
    """测试中文数字文本 → 整数转换。"""

    def test_empty_string_returns_zero(self):
        assert normalize_count("") == 0

    def test_none_returns_zero(self):
        assert normalize_count(None) == 0

    def test_wan_notation(self):
        assert normalize_count("1.2万") == 12000

    def test_w_notation_lowercase(self):
        assert normalize_count("3.5w") == 35000

    def test_w_notation_uppercase(self):
        assert normalize_count("3.5W") == 35000

    def test_integer_string(self):
        assert normalize_count("324") == 324

    def test_zero_string(self):
        assert normalize_count("0") == 0

    def test_comma_separated_number(self):
        assert normalize_count("3,240") == 3240

    def test_whole_wan_unit(self):
        assert normalize_count("2万") == 20000

    def test_invalid_text_returns_zero(self):
        assert normalize_count("赞") == 0

    def test_strips_leading_and_trailing_whitespace(self):
        assert normalize_count("  500  ") == 500

    def test_float_truncated_to_int(self):
        """浮点数应截断为整数（非四舍五入）。"""
        assert normalize_count("1.9") == 1

    def test_wan_with_space_between_number_and_unit(self):
        """数字与单位之间有空格也应正确解析。"""
        assert normalize_count("1.2 万") == 12000


# ============================================================
# _query_text（辅助函数）
# ============================================================


class TestQueryText:
    """测试 _query_text 按优先级尝试选择器。"""

    async def test_returns_text_from_first_matching_selector(self):
        """第一个命中的选择器应返回其文本。"""
        mock_page = AsyncMock()
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value="  标题内容  ")

        async def qs(sel):
            return el if sel == ".title" else None

        mock_page.query_selector = qs
        result = await _query_text(mock_page, [".other", ".title"])
        assert result == "标题内容"

    async def test_falls_back_when_first_selector_returns_none(self):
        """第一个选择器未命中时应继续尝试下一个。"""
        mock_page = AsyncMock()
        backup_el = AsyncMock()
        backup_el.inner_text = AsyncMock(return_value="备用文本")

        async def qs(sel):
            return backup_el if sel == ".backup" else None

        mock_page.query_selector = qs
        result = await _query_text(mock_page, [".primary", ".backup"])
        assert result == "备用文本"

    async def test_returns_empty_when_no_selector_matches(self):
        """所有选择器均未命中时应返回空字符串。"""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        result = await _query_text(mock_page, [".a", ".b"])
        assert result == ""

    async def test_skips_element_with_empty_text(self):
        """元素存在但文本为空时，应继续尝试下一个选择器。"""
        mock_page = AsyncMock()
        empty_el = AsyncMock()
        empty_el.inner_text = AsyncMock(return_value="   ")
        real_el = AsyncMock()
        real_el.inner_text = AsyncMock(return_value="真实内容")
        call_count = 0

        async def qs(sel):
            nonlocal call_count
            call_count += 1
            return empty_el if call_count == 1 else real_el

        mock_page.query_selector = qs
        result = await _query_text(mock_page, [".empty", ".real"])
        assert result == "真实内容"


# ============================================================
# _parse_interact_count（辅助函数）
# ============================================================


class TestParseInteractCount:
    """测试 _parse_interact_count 互动计数提取。"""

    async def test_returns_parsed_count_from_matching_selector(self):
        """命中选择器后应返回解析的整数计数。"""
        mock_page = AsyncMock()
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value="1.2万")
        mock_page.query_selector = AsyncMock(return_value=el)
        result = await _parse_interact_count(mock_page, [".likes"])
        assert result == 12000

    async def test_returns_zero_when_no_selector_matches(self):
        """所有选择器均未命中时应返回 0。"""
        mock_page = AsyncMock()
        mock_page.query_selector = AsyncMock(return_value=None)
        result = await _parse_interact_count(mock_page, [".a", ".b"])
        assert result == 0

    async def test_returns_zero_for_empty_text(self):
        """元素存在但文本为空时应返回 0。"""
        mock_page = AsyncMock()
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value="  ")
        mock_page.query_selector = AsyncMock(return_value=el)
        result = await _parse_interact_count(mock_page, [".count"])
        assert result == 0


# ============================================================
# parse_search_card
# ============================================================


def _make_text_el(text: str) -> AsyncMock:
    """创建带固定文本的模拟元素。"""
    el = AsyncMock()
    el.inner_text = AsyncMock(return_value=text)
    return el


def _make_attr_el(attr_value: str) -> AsyncMock:
    """创建 get_attribute 返回固定值的模拟元素。"""
    el = AsyncMock()
    el.get_attribute = AsyncMock(return_value=attr_value)
    return el


def _make_search_card(
    explore_href: str = "/explore/abc123",
    cover_href: str = "/search_result/abc123?xsec_token=TOKEN123&xsec_source=pc_search",
    img_data_src: str = "https://example.com/cover.jpg",
    title: str = "测试标题",
    author: str = "测试作者",
    user_href: str = "/user/profile/user001?x=1",
    publish_time: str = "2025-01-15",
    likes_text: str = "1.2万",
    is_video: bool = False,
    has_explore_anchor: bool = True,
) -> AsyncMock:
    """创建可配置的模拟搜索结果卡片 ElementHandle。"""
    explore_anchor = _make_attr_el(explore_href) if has_explore_anchor else None
    cover_anchor = _make_attr_el(cover_href)

    async def img_get_attr(name):
        if name == "data-src":
            return img_data_src
        return None

    img_el = AsyncMock()
    img_el.get_attribute = img_get_attr

    title_el = _make_text_el(title)
    author_el = _make_text_el(author)
    user_anchor = _make_attr_el(user_href)
    time_el = _make_text_el(publish_time)
    like_el = _make_text_el(likes_text)
    video_el = AsyncMock() if is_video else None

    async def query_selector(sel: str):
        if 'a[href*="/explore/"]' in sel:
            return explore_anchor
        if sel == "a.cover":
            return cover_anchor
        if sel == "a.cover img":
            return img_el
        if ".footer a.title span" in sel or ".footer a.title" in sel:
            return title_el
        if ".card-bottom-wrapper .author .name" in sel:
            return author_el
        if "a.author[href*='/user/profile/']" in sel:
            return user_anchor
        if ".name-time-wrapper .time" in sel:
            return time_el
        if ".like-wrapper .count" in sel:
            return like_el
        if "video-icon" in sel or "type-video" in sel or "play-icon" in sel:
            return video_el
        return None

    card = AsyncMock()
    card.query_selector = query_selector
    return card


class TestParseSearchCard:
    """测试搜索结果卡片解析。"""

    async def test_extracts_note_id_from_explore_href(self):
        """应从 /explore/ 链接末段提取 note_id。"""
        card = _make_search_card(explore_href="/explore/abc123def456")
        result = await parse_search_card(card)
        assert result is not None
        assert result["note_id"] == "abc123def456"

    async def test_builds_url_with_xsec_token(self):
        """应拼装包含 xsec_token 的完整 note_url。"""
        card = _make_search_card(
            cover_href="/search_result/abc123?xsec_token=MYTOKEN&xsec_source=pc_search"
        )
        result = await parse_search_card(card)
        assert result is not None
        assert "xsec_token=MYTOKEN" in result["note_url"]
        assert "xiaohongshu.com" in result["note_url"]

    async def test_builds_url_without_xsec_token(self):
        """封面链接无 xsec_token 时应使用不含 token 的 URL。"""
        card = _make_search_card(cover_href="/search_result/abc123")
        result = await parse_search_card(card)
        assert result is not None
        # 无 token 时 URL 格式：/explore/{note_id}
        assert "xsec_token" not in result["note_url"]

    async def test_falls_back_to_cover_anchor_for_note_id(self):
        """无 /explore/ 链接时，应从封面链接提取 note_id。"""
        card = _make_search_card(
            has_explore_anchor=False,
            cover_href="/search_result/fallback123?xsec_token=T",
        )
        result = await parse_search_card(card)
        assert result is not None
        assert result["note_id"] == "fallback123"

    async def test_returns_none_when_no_note_id(self):
        """无法提取 note_id 时应返回 None。"""
        card = AsyncMock()
        card.query_selector = AsyncMock(return_value=None)
        result = await parse_search_card(card)
        assert result is None

    async def test_parses_title(self):
        """应正确提取标题文本。"""
        card = _make_search_card(title="Python 进阶技巧")
        result = await parse_search_card(card)
        assert result is not None
        assert result["title"] == "Python 进阶技巧"

    async def test_parses_author(self):
        """应正确提取作者昵称。"""
        card = _make_search_card(author="测试用户名")
        result = await parse_search_card(card)
        assert result is not None
        assert result["author"] == "测试用户名"

    async def test_parses_author_id_from_user_profile_href(self):
        """应从用户主页链接提取 author_id。"""
        card = _make_search_card(user_href="/user/profile/UserID001?extra=x")
        result = await parse_search_card(card)
        assert result is not None
        assert result["author_id"] == "UserID001"

    async def test_parses_likes_count(self):
        """应正确解析点赞数文本（含万单位）。"""
        card = _make_search_card(likes_text="3.5万")
        result = await parse_search_card(card)
        assert result is not None
        assert result["likes"] == 35000

    async def test_note_type_image_by_default(self):
        """无视频标记时笔记类型应为 'image'。"""
        card = _make_search_card(is_video=False)
        result = await parse_search_card(card)
        assert result is not None
        assert result["note_type"] == "image"

    async def test_note_type_video_when_video_marker_present(self):
        """有视频标记时笔记类型应为 'video'。"""
        card = _make_search_card(is_video=True)
        result = await parse_search_card(card)
        assert result is not None
        assert result["note_type"] == "video"

    async def test_result_contains_all_required_keys(self):
        """返回字典应包含所有必需字段。"""
        card = _make_search_card()
        result = await parse_search_card(card)
        assert result is not None
        required = {
            "note_id", "title", "author", "author_id",
            "cover_url", "likes", "note_url", "note_type", "publish_time",
        }
        assert required.issubset(set(result.keys()))

    async def test_returns_none_on_exception(self):
        """解析过程发生异常时应捕获并返回 None。"""
        card = AsyncMock()
        card.query_selector = AsyncMock(side_effect=Exception("DOM error"))
        result = await parse_search_card(card)
        assert result is None

    async def test_cover_url_from_img_src_fallback(self):
        """封面图 data-src 为空时应回退到 src 属性。"""
        # 创建只有 src 没有 data-src 的 img 元素
        async def img_get_attr(name):
            if name == "src":
                return "https://example.com/via-src.jpg"
            return None  # data-src is None

        img_el = AsyncMock()
        img_el.get_attribute = img_get_attr

        explore_anchor = _make_attr_el("/explore/abc123")
        cover_anchor = _make_attr_el("/search_result/abc123?xsec_token=T")
        title_el = _make_text_el("标题")
        author_el = _make_text_el("作者")
        user_anchor = _make_attr_el("/user/profile/u1")
        time_el = _make_text_el("2025-01-15")
        like_el = _make_text_el("100")

        async def qs(sel):
            if 'a[href*="/explore/"]' in sel:
                return explore_anchor
            if sel == "a.cover":
                return cover_anchor
            if sel == "a.cover img":
                return img_el
            if ".footer a.title span" in sel:
                return title_el
            if ".card-bottom-wrapper .author .name" in sel:
                return author_el
            if "a.author[href*='/user/profile/']" in sel:
                return user_anchor
            if ".name-time-wrapper .time" in sel:
                return time_el
            if ".like-wrapper .count" in sel:
                return like_el
            return None

        card = AsyncMock()
        card.query_selector = qs
        result = await parse_search_card(card)
        assert result is not None
        assert result["cover_url"] == "https://example.com/via-src.jpg"


# ============================================================
# parse_note_detail
# ============================================================


def _make_note_page(
    title: str = "笔记标题",
    content: str = "笔记正文内容",
    author: str = "作者昵称",
    author_id: str = "user001",
    publish_time: str = "2025-01-15",
    likes: int = 1200,
    collects: int = 300,
    comments_count: int = 50,
    shares: int = 10,
    tags: list[str] | None = None,
    images: list[str] | None = None,
) -> AsyncMock:
    """创建模拟笔记详情页 Page。"""
    tags = tags or ["#Python", "#教程"]
    images = images or ["https://example.com/img1.jpg"]

    def make_el(text):
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=text)
        return el

    title_el = make_el(title)
    content_el = make_el(content)
    author_el = make_el(author)
    time_el = make_el(publish_time)
    likes_el = make_el(str(likes))
    collects_el = make_el(str(collects))
    comments_el = make_el(str(comments_count))
    shares_el = make_el(str(shares))

    author_link = AsyncMock()
    author_link.get_attribute = AsyncMock(return_value=f"/user/profile/{author_id}?x=1")

    async def query_selector(sel: str):
        if sel == "#detail-title":
            return title_el
        if sel == "#detail-desc .note-text":
            return content_el
        if sel == ".author-container .username":
            return author_el
        if sel == ".note-content .bottom-container .date":
            return time_el
        if ".author-container a[href*='/user/profile/']" in sel:
            return author_link
        if ".like-wrapper .count" in sel:
            return likes_el
        if ".collect-wrapper .count" in sel:
            return collects_el
        if ".chat-wrapper .count" in sel:
            return comments_el
        if ".share-wrapper .count" in sel:
            return shares_el
        return None

    # 图片 mock
    img_els = []
    for src in images:
        img_el = AsyncMock()

        async def get_attr_fn(name, _src=src):
            if name == "data-src":
                return _src
            return None

        img_el.get_attribute = get_attr_fn
        img_els.append(img_el)

    async def query_selector_all(sel: str):
        if sel == "#detail-desc a.tag":
            return [make_el(tag) for tag in tags]
        if ".swiper-slide img" in sel:
            return img_els
        return []

    mock_page = AsyncMock()
    mock_page.query_selector = query_selector
    mock_page.query_selector_all = query_selector_all
    return mock_page


class TestParseNoteDetail:
    """测试笔记详情页解析。"""

    async def test_parses_title_and_content(self):
        """应正确解析标题与正文。"""
        page = _make_note_page(title="Python 教程", content="详细内容")
        result = await parse_note_detail(page, "note123")
        assert result is not None
        assert result["title"] == "Python 教程"
        assert result["content"] == "详细内容"

    async def test_preserves_passed_note_id(self):
        """note_id 应使用调用方传入的值。"""
        page = _make_note_page()
        result = await parse_note_detail(page, "my_note_id")
        assert result is not None
        assert result["note_id"] == "my_note_id"

    async def test_parses_author_and_author_id(self):
        """应正确解析作者昵称与 ID。"""
        page = _make_note_page(author="博主张三", author_id="ZhangSan007")
        result = await parse_note_detail(page, "note123")
        assert result is not None
        assert result["author"] == "博主张三"
        assert result["author_id"] == "ZhangSan007"

    async def test_parses_interaction_counts(self):
        """应正确解析点赞、收藏、评论、分享计数。"""
        page = _make_note_page(likes=5000, collects=200, comments_count=88, shares=15)
        result = await parse_note_detail(page, "note123")
        assert result is not None
        assert result["likes"] == 5000
        assert result["collects"] == 200
        assert result["comments_count"] == 88
        assert result["shares"] == 15

    async def test_parses_tags_strips_hash(self):
        """标签应去掉 # 前缀。"""
        page = _make_note_page(tags=["#Python", "#机器学习"])
        result = await parse_note_detail(page, "note123")
        assert result is not None
        assert "Python" in result["tags"]
        assert "机器学习" in result["tags"]
        # 原始 # 不应出现
        for tag in result["tags"]:
            assert not tag.startswith("#")

    async def test_parses_images(self):
        """应正确提取图片 URL 列表。"""
        images = ["https://example.com/a.jpg", "https://example.com/b.jpg"]
        page = _make_note_page(images=images)
        result = await parse_note_detail(page, "note123")
        assert result is not None
        assert set(result["images"]) == set(images)

    async def test_result_contains_all_required_keys(self):
        """返回字典应包含所有必需字段。"""
        page = _make_note_page()
        result = await parse_note_detail(page, "note123")
        assert result is not None
        required = {
            "note_id", "title", "content", "author", "author_id",
            "publish_time", "likes", "collects", "comments_count",
            "shares", "tags", "images", "note_type", "video_url",
        }
        assert required.issubset(set(result.keys()))

    async def test_returns_none_on_exception(self):
        """解析过程发生异常时应捕获并返回 None。"""
        page = AsyncMock()
        page.query_selector = AsyncMock(side_effect=Exception("parse error"))
        page.query_selector_all = AsyncMock(side_effect=Exception("parse error"))
        result = await parse_note_detail(page, "note123")
        assert result is None


# ============================================================
# parse_comment
# ============================================================


def _make_comment_el(
    comment_id: str = "comment-abc123",
    user_name: str = "评论用户",
    user_id: str = "usr001",
    content: str = "测试评论内容",
    likes_text: str = "10",
    time_date: str = "01-15",
    ip_location: str = "广东",
    no_location: bool = False,
) -> AsyncMock:
    """创建模拟评论 ElementHandle。"""
    comment_el = AsyncMock()
    comment_el.get_attribute = AsyncMock(return_value=comment_id)

    def make_el(text):
        el = AsyncMock()
        el.inner_text = AsyncMock(return_value=text)
        return el

    user_name_el = make_el(user_name)
    user_link = AsyncMock()
    user_link.get_attribute = AsyncMock(return_value=f"/user/profile/{user_id}?x=1")
    content_el = make_el(content)
    like_el = make_el(likes_text)
    loc_el = make_el(ip_location) if not no_location else None
    # date 包含时间 + 属地（如果有）
    full_date = f"{time_date}{ip_location}" if ip_location and not no_location else time_date
    date_el = make_el(full_date)

    async def query_selector(sel: str):
        if ".right .author-wrapper .author a.name" in sel:
            return user_name_el
        if ".right .author-wrapper a[href*='/user/profile/']" in sel:
            return user_link
        if ".right .content .note-text" in sel:
            return content_el
        if ".right .info .interactions .like" in sel:
            return like_el
        if ".right .info .date .location" in sel:
            return loc_el
        if sel == ".right .info .date":
            return date_el
        return None

    comment_el.query_selector = query_selector
    return comment_el


class TestParseComment:
    """测试单条评论解析。"""

    async def test_strips_comment_prefix_from_id(self):
        """应去掉 'comment-' 前缀，保留纯 ID。"""
        el = _make_comment_el(comment_id="comment-xyz789")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["comment_id"] == "xyz789"

    async def test_parses_user_name(self):
        """应正确提取评论用户昵称。"""
        el = _make_comment_el(user_name="李四")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["user_name"] == "李四"

    async def test_parses_user_id(self):
        """应从用户主页链接提取 user_id。"""
        el = _make_comment_el(user_id="UserXYZ")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["user_id"] == "UserXYZ"

    async def test_parses_content(self):
        """应正确提取评论正文。"""
        el = _make_comment_el(content="这条评论很有用")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["content"] == "这条评论很有用"

    async def test_parses_likes_count(self):
        """应正确解析点赞数。"""
        el = _make_comment_el(likes_text="500")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["likes"] == 500

    async def test_likes_zero_when_text_is_zan(self):
        """点赞文本为 '赞' 时（无人点赞）应返回 0。"""
        el = _make_comment_el(likes_text="赞")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["likes"] == 0

    async def test_strips_ip_location_from_time(self):
        """时间字段应去掉尾部的 IP 属地部分。"""
        el = _make_comment_el(time_date="01-15", ip_location="广东")
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["time"] == "01-15"
        assert result["ip_location"] == "广东"

    async def test_time_preserved_when_no_ip_location(self):
        """无 IP 属地时，时间字段应为 .date 容器的完整文本。"""
        el = _make_comment_el(time_date="01-20", no_location=True)
        result = await parse_comment(el, "note123")
        assert result is not None
        assert result["time"] == "01-20"
        assert result["ip_location"] == ""

    async def test_note_id_preserved(self):
        """note_id 应保留为传入的值。"""
        el = _make_comment_el()
        result = await parse_comment(el, "parent_note_999")
        assert result is not None
        assert result["note_id"] == "parent_note_999"

    async def test_result_contains_all_required_keys(self):
        """返回字典应包含所有必需字段。"""
        el = _make_comment_el()
        result = await parse_comment(el, "note123")
        assert result is not None
        required = {
            "comment_id", "note_id", "user_name", "user_id",
            "content", "likes", "time", "ip_location",
        }
        assert required.issubset(set(result.keys()))

    async def test_returns_none_on_exception(self):
        """解析异常时应捕获并返回 None。"""
        el = AsyncMock()
        el.get_attribute = AsyncMock(side_effect=Exception("DOM error"))
        result = await parse_comment(el, "note123")
        assert result is None
