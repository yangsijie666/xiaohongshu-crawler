"""
数据解析模块

职责：
  - 将 Playwright DOM 元素转换为结构化 Python 数据
  - 处理数字格式转换（"1.2万" → 12000）
  - 统一处理缺失字段的默认值
  - 清洗文本（去除多余空白）

覆盖范围：
  - 搜索结果卡片解析（Phase 2）
  - 笔记详情页解析（Phase 3）
  - 评论区解析（Phase 3）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

logger = logging.getLogger(__name__)

# 小红书笔记详情页前缀
_NOTE_BASE_URL = "https://www.xiaohongshu.com"


def normalize_count(text: str) -> int:
    """将中文数字文本转换为整数。

    支持格式：
      - "1.2万" → 12000
      - "3.5w" → 35000
      - "324" → 324
      - "" / None → 0

    Args:
        text: 原始文本字符串

    Returns:
        整数值，解析失败返回 0
    """
    if not text:
        return 0

    text = text.strip().replace(",", "")

    # 匹配 "1.2万" 或 "1.2w"（大小写不敏感）
    match = re.match(r"^([\d.]+)\s*[万wW]$", text)
    if match:
        try:
            return int(float(match.group(1)) * 10_000)
        except ValueError:
            return 0

    # 纯数字
    try:
        return int(float(text))
    except ValueError:
        return 0


async def parse_search_card(card: "ElementHandle") -> dict | None:
    """解析搜索结果卡片元素，返回结构化笔记摘要数据。

    从单个卡片 DOM 元素中提取：
      - note_id：笔记唯一 ID（从 URL 末段提取）
      - title：笔记标题（纯图片笔记可能为空）
      - author：作者昵称
      - author_id：作者 ID（从用户主页 URL 提取）
      - cover_url：封面图片 URL
      - likes：点赞数（整数）
      - note_url：笔记详情页完整 URL（优先使用 /explore/ 路径）
      - note_type：笔记类型（"video" / "image"）
      - publish_time：发布时间（如 "2025-12-05"）

    Args:
        card: 单个搜索结果卡片的 ElementHandle

    Returns:
        包含上述字段的字典，解析失败返回 None
    """
    try:
        # ---- 笔记 URL 与 ID ----
        # 卡片内有两种链接：
        #   1. 隐藏的 <a href="/explore/{note_id}">（无 token，直接导航会 404）
        #   2. 封面 <a class="cover" href="/search_result/{note_id}?xsec_token=...">
        # 策略：从隐藏链接提取 note_id，从封面链接获取 xsec_token，
        #        拼装为 /explore/{note_id}?xsec_token=...&xsec_source=pc_search
        note_url: str = ""
        note_id: str = ""
        xsec_token: str = ""

        # 从隐藏的 /explore/ 链接提取 note_id
        explore_anchor = await card.query_selector('a[href*="/explore/"]')
        if explore_anchor:
            href = await explore_anchor.get_attribute("href") or ""
            if href:
                note_id = href.split("?")[0].rstrip("/").split("/")[-1]

        # 从封面 <a class="cover"> 链接提取 xsec_token
        cover_anchor = await card.query_selector("a.cover")
        if cover_anchor:
            cover_href = await cover_anchor.get_attribute("href") or ""
            # 格式: /search_result/{note_id}?xsec_token=...&xsec_source=
            token_match = re.search(r"xsec_token=([^&]+)", cover_href)
            if token_match:
                xsec_token = token_match.group(1)
            # 若隐藏链接未提取到 note_id，从封面链接降级提取
            if not note_id:
                note_id = cover_href.split("?")[0].rstrip("/").split("/")[-1]

        if not note_id:
            logger.warning("卡片缺少 note_id，跳过")
            return None

        # 拼装完整 URL（携带 xsec_token 以避免 403/404 拦截）
        if xsec_token:
            note_url = (
                f"{_NOTE_BASE_URL}/explore/{note_id}"
                f"?xsec_token={xsec_token}&xsec_source=pc_search"
            )
        else:
            note_url = f"{_NOTE_BASE_URL}/explore/{note_id}"

        # ---- 封面图片 ----
        # 封面 <img> 在 <a class="cover"> 内，排除作者头像（.author-avatar）
        cover_url: str = ""
        img_el = await card.query_selector("a.cover img")
        if img_el is None:
            img_el = await card.query_selector("img:not(.author-avatar)")
        if img_el:
            cover_url = (
                await img_el.get_attribute("data-src")
                or await img_el.get_attribute("src")
                or ""
            )

        # ---- 标题 ----
        # 实际结构：.footer > a.title > span（纯图片笔记可能无标题元素）
        title: str = ""
        for sel in (
            ".footer a.title span",         # 精确匹配：footer 内 a.title 下的 span
            ".footer a.title",               # a.title 自身的文本
            ".footer .title span",           # 降级：.title 下的 span
            ".footer .title",                # 降级：.title 自身
            "a.title span",                  # 无 .footer 包裹时
            "a.title",
        ):
            title_el = await card.query_selector(sel)
            if title_el:
                title = (await title_el.inner_text()).strip()
                if title:
                    break

        # ---- 作者信息 ----
        # 实际结构：.card-bottom-wrapper > a.author > .name-time-wrapper > .name
        author: str = ""
        author_id: str = ""
        for sel in (
            ".card-bottom-wrapper .author .name",   # 精确匹配
            ".card-bottom-wrapper .name",            # 降级
            ".author-wrapper .name",                 # 旧版结构
            ".author .name",                         # 通用降级
        ):
            author_el = await card.query_selector(sel)
            if author_el:
                author = (await author_el.inner_text()).strip()
                if author:
                    break

        # 从用户主页链接提取 author_id
        # 实际结构：a.author[href*='/user/profile/{id}?...']
        for sel in (
            ".card-bottom-wrapper a.author[href*='/user/profile/']",
            "a.author[href*='/user/profile/']",
            "a[href*='/user/profile/']",
        ):
            user_anchor = await card.query_selector(sel)
            if user_anchor:
                user_href = await user_anchor.get_attribute("href") or ""
                parts = user_href.split("/user/profile/")
                if len(parts) == 2:
                    author_id = parts[1].split("?")[0].rstrip("/")
                    break

        # ---- 发布时间 ----
        # 实际结构：.name-time-wrapper > .time
        publish_time: str = ""
        for sel in (".name-time-wrapper .time", ".time"):
            time_el = await card.query_selector(sel)
            if time_el:
                publish_time = (await time_el.inner_text()).strip()
                if publish_time:
                    break

        # ---- 点赞数 ----
        likes: int = 0
        for sel in (".like-wrapper .count", ".likes .count", ".count"):
            like_el = await card.query_selector(sel)
            if like_el:
                likes_text = (await like_el.inner_text()).strip()
                likes = normalize_count(likes_text)
                break

        # ---- 笔记类型 ----
        note_type: str = "image"
        video_marker = await card.query_selector(
            ".video-icon, .type-video, [class*='play-icon']"
        )
        if video_marker:
            note_type = "video"

        return {
            "note_id": note_id,
            "title": title,
            "author": author,
            "author_id": author_id,
            "cover_url": cover_url,
            "likes": likes,
            "note_url": note_url,
            "note_type": note_type,
            "publish_time": publish_time,
        }

    except Exception as e:
        logger.warning("解析搜索卡片失败：%s", e, exc_info=True)
        return None


# ---------- 笔记详情页解析（Phase 3） ----------

# 笔记详情页各字段的候选选择器（按优先级排列）
# 真实 DOM：#noteContainer > .interaction-container > .note-scroller > .note-content
_DETAIL_TITLE_SELECTORS = [
    "#detail-title",
    ".note-content .title",
]

_DETAIL_CONTENT_SELECTORS = [
    "#detail-desc .note-text",
    "#detail-desc",
    ".note-content .desc",
]

# 真实 DOM：.interaction-container > .author-container > .author-wrapper > .info > .username
_DETAIL_AUTHOR_SELECTORS = [
    ".author-container .username",
    ".interaction-container .username",
    ".author-wrapper .username",
]

_DETAIL_AUTHOR_LINK_SELECTORS = [
    ".author-container a[href*='/user/profile/']",
    ".interaction-container a[href*='/user/profile/']",
]

# 真实 DOM：.note-content > .bottom-container > span.date
_DETAIL_TIME_SELECTORS = [
    ".note-content .bottom-container .date",
    ".bottom-container .date",
]

# 真实 DOM：#detail-desc a#hash-tag.tag
_DETAIL_TAG_SELECTOR = "#detail-desc a.tag"

# 真实 DOM：.swiper-slide img
_DETAIL_IMAGE_SELECTORS = [
    ".swiper-slide img",
    ".media-container img",
]

_DETAIL_VIDEO_SELECTORS = [
    ".player-container video source",
    "video source",
    ".player-container video",
    "video",
]


async def _query_text(page: "Page", selectors: list[str]) -> str:
    """在页面中按优先级尝试多个选择器，返回第一个非空文本。"""
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            if text:
                return text
    return ""


async def parse_note_detail(page: "Page", note_id: str) -> dict | None:
    """解析笔记详情页，返回结构化数据。

    从当前已加载的笔记详情页中提取：
      - note_id / title / content / author / author_id
      - publish_time / likes / collects / comments_count / shares
      - tags / images / note_type / video_url

    Args:
        page: 已加载笔记详情页的 Playwright Page 对象
        note_id: 笔记 ID（由调用方传入）

    Returns:
        包含上述字段的字典，解析失败返回 None
    """
    try:
        # ---- 标题 ----
        title = await _query_text(page, _DETAIL_TITLE_SELECTORS)

        # ---- 正文内容 ----
        content = await _query_text(page, _DETAIL_CONTENT_SELECTORS)

        # ---- 作者昵称 ----
        author = await _query_text(page, _DETAIL_AUTHOR_SELECTORS)

        # ---- 作者 ID ----
        author_id = ""
        for sel in _DETAIL_AUTHOR_LINK_SELECTORS:
            anchor = await page.query_selector(sel)
            if anchor:
                href = await anchor.get_attribute("href") or ""
                parts = href.split("/user/profile/")
                if len(parts) == 2:
                    author_id = parts[1].split("?")[0].rstrip("/")
                    break

        # ---- 发布时间 ----
        publish_time = await _query_text(page, _DETAIL_TIME_SELECTORS)

        # ---- 互动数据 ----
        # 真实 DOM：.interact-container 内有 .like-wrapper / .collect-wrapper / .chat-wrapper
        # 每个 wrapper 内有 span.count 显示数字
        likes = await _parse_interact_count(page, [
            ".interact-container .like-wrapper .count",
            ".engage-bar .like-wrapper .count",
            ".like-wrapper .count",
        ])
        collects = await _parse_interact_count(page, [
            ".interact-container .collect-wrapper .count",
            ".engage-bar .collect-wrapper .count",
            ".collect-wrapper .count",
        ])
        comments_count = await _parse_interact_count(page, [
            ".interact-container .chat-wrapper .count",
            ".engage-bar .chat-wrapper .count",
            ".chat-wrapper .count",
        ])
        shares = await _parse_interact_count(page, [
            ".interact-container .share-wrapper .count",
            ".engage-bar .share-wrapper .count",
            ".share-wrapper .count",
        ])

        # ---- 标签 ----
        tags: list[str] = []
        tag_els = await page.query_selector_all(_DETAIL_TAG_SELECTOR)
        for tag_el in tag_els:
            tag_text = (await tag_el.inner_text()).strip().lstrip("#")
            if tag_text:
                tags.append(tag_text)

        # ---- 图片列表 ----
        images: list[str] = []
        for sel in _DETAIL_IMAGE_SELECTORS:
            img_els = await page.query_selector_all(sel)
            if img_els:
                for img_el in img_els:
                    src = (
                        await img_el.get_attribute("data-src")
                        or await img_el.get_attribute("src")
                        or ""
                    )
                    if src and src not in images:
                        images.append(src)
                break  # 仅使用第一个命中的选择器

        # ---- 视频 URL 与笔记类型 ----
        video_url = ""
        note_type = "image"
        for sel in _DETAIL_VIDEO_SELECTORS:
            video_el = await page.query_selector(sel)
            if video_el:
                video_url = (
                    await video_el.get_attribute("src")
                    or await video_el.get_attribute("data-src")
                    or ""
                )
                note_type = "video"
                break

        return {
            "note_id": note_id,
            "title": title,
            "content": content,
            "author": author,
            "author_id": author_id,
            "publish_time": publish_time,
            "likes": likes,
            "collects": collects,
            "comments_count": comments_count,
            "shares": shares,
            "tags": tags,
            "images": images,
            "note_type": note_type,
            "video_url": video_url,
        }

    except Exception as e:
        logger.warning("解析笔记详情失败（note_id=%s）：%s", note_id, e, exc_info=True)
        return None


async def _parse_interact_count(page: "Page", selectors: list[str]) -> int:
    """在页面中按优先级尝试选择器提取互动计数。"""
    for sel in selectors:
        el = await page.query_selector(sel)
        if el:
            text = (await el.inner_text()).strip()
            if text:
                return normalize_count(text)
    return 0


# ---------- 评论解析（Phase 3） ----------

# 评论区各字段的候选选择器
# 真实 DOM：.comment-item > .comment-inner-container > .right > ...
_COMMENT_USER_SELECTORS = [
    ".right .author-wrapper .author a.name",  # 精确路径
    ".right .author a.name",
    ".author a.name",
    "a.name",
]

_COMMENT_USER_LINK_SELECTORS = [
    ".right .author-wrapper a[href*='/user/profile/']",
    "a[href*='/user/profile/']",
]

_COMMENT_CONTENT_SELECTORS = [
    ".right .content .note-text",
    ".right .content",
]

# 真实 DOM：.right > .info > .interactions > .like（inner_text 为数字或"赞"）
_COMMENT_LIKE_SELECTORS = [
    ".right .info .interactions .like",
    ".info .like",
]

# 真实 DOM：.right > .info > .date > span:first-child（不含 .location）
# 注意：.date 的 inner_text 包含日期+属地（如 "01-15广东"），需分别提取
_COMMENT_TIME_SELECTOR = ".right .info .date"

# 真实 DOM：.right > .info > .date > span.location
_COMMENT_LOCATION_SELECTORS = [
    ".right .info .date .location",
    ".info .location",
    ".location",
]


async def parse_comment(comment_el: "ElementHandle", note_id: str) -> dict | None:
    """解析单条评论元素，返回结构化数据。

    真实 DOM 结构：
      .comment-item#comment-{id}
        .comment-inner-container
          .avatar
          .right
            .author-wrapper > .author > a.name
            .content > span.note-text
            .info
              .date > span (时间) + span.location (IP 属地)
              .interactions > .like (点赞数)

    Args:
        comment_el: 单条评论的 ElementHandle（.comment-item 元素）
        note_id: 所属笔记 ID

    Returns:
        包含 comment_id / note_id / user_name / user_id /
        content / likes / time / ip_location 的字典，失败返回 None
    """
    try:
        # ---- 评论 ID ----
        # 真实 DOM 中 id 格式为 "comment-{hex_id}"，需去掉前缀
        raw_id = await comment_el.get_attribute("id") or ""
        comment_id = raw_id.removeprefix("comment-") if raw_id else ""

        # ---- 评论者昵称 ----
        user_name = ""
        for sel in _COMMENT_USER_SELECTORS:
            el = await comment_el.query_selector(sel)
            if el:
                user_name = (await el.inner_text()).strip()
                if user_name:
                    break

        # ---- 评论者 ID ----
        user_id = ""
        for sel in _COMMENT_USER_LINK_SELECTORS:
            anchor = await comment_el.query_selector(sel)
            if anchor:
                href = await anchor.get_attribute("href") or ""
                parts = href.split("/user/profile/")
                if len(parts) == 2:
                    user_id = parts[1].split("?")[0].rstrip("/")
                    break

        # ---- 评论内容 ----
        content = ""
        for sel in _COMMENT_CONTENT_SELECTORS:
            el = await comment_el.query_selector(sel)
            if el:
                content = (await el.inner_text()).strip()
                if content:
                    break

        # ---- 点赞数 ----
        # .like 的 inner_text 为数字（如 "10"）或 "赞"（无人点赞）
        likes = 0
        for sel in _COMMENT_LIKE_SELECTORS:
            el = await comment_el.query_selector(sel)
            if el:
                text = (await el.inner_text()).strip()
                if text and text != "赞":
                    likes = normalize_count(text)
                break

        # ---- 评论时间 & IP 属地 ----
        # .date 容器内：<span>01-15</span><span class="location">广东</span>
        time_text = ""
        ip_location = ""

        # 先提取 IP 属地
        for sel in _COMMENT_LOCATION_SELECTORS:
            loc_el = await comment_el.query_selector(sel)
            if loc_el:
                ip_location = (await loc_el.inner_text()).strip()
                break

        # 从 .date 容器提取完整文本，去掉属地部分得到纯时间
        date_el = await comment_el.query_selector(_COMMENT_TIME_SELECTOR)
        if date_el:
            full_date = (await date_el.inner_text()).strip()
            if ip_location and full_date.endswith(ip_location):
                time_text = full_date[: -len(ip_location)].strip()
            else:
                time_text = full_date

        return {
            "comment_id": comment_id,
            "note_id": note_id,
            "user_name": user_name,
            "user_id": user_id,
            "content": content,
            "likes": likes,
            "time": time_text,
            "ip_location": ip_location,
        }

    except Exception as e:
        logger.warning("解析评论失败（note_id=%s）：%s", note_id, e, exc_info=True)
        return None
