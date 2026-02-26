"""
数据解析模块

职责：
  - 将 Playwright DOM 元素转换为结构化 Python 数据
  - 处理数字格式转换（"1.2万" → 12000）
  - 统一处理缺失字段的默认值
  - 清洗文本（去除多余空白）

当前覆盖：搜索结果卡片解析
后续扩展：笔记详情页、评论区解析（Phase 3）
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle

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
        # 卡片内有隐藏的 <a href="/explore/{note_id}"> 链接，URL 更干净（无 xsec_token）
        # 若该链接不存在，降级使用封面 <a class="cover"> 的 href
        note_url: str = ""
        note_id: str = ""

        # 优先：隐藏的 /explore/ 链接（display:none 但 DOM 中存在）
        explore_anchor = await card.query_selector('a[href*="/explore/"]')
        if explore_anchor:
            href = await explore_anchor.get_attribute("href") or ""
            if href:
                note_url = _NOTE_BASE_URL + href if href.startswith("/") else href
                note_id = href.split("?")[0].rstrip("/").split("/")[-1]

        # 降级：封面 <a class="cover"> 链接
        if not note_id:
            cover_anchor = await card.query_selector("a.cover")
            if cover_anchor is None:
                cover_anchor = await card.query_selector("a")
            if cover_anchor:
                href = await cover_anchor.get_attribute("href") or ""
                if href.startswith("/"):
                    note_url = _NOTE_BASE_URL + href
                elif href.startswith("http"):
                    note_url = href
                note_id = href.split("?")[0].rstrip("/").split("/")[-1]

        if not note_id:
            logger.warning("卡片缺少 note_id，跳过")
            return None

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
