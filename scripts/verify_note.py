"""
Phase 3 笔记详情 + 评论采集验证脚本

验证详情采集的完整链路：
  1. 复用已有登录态（须先完成登录）
  2. 按关键词搜索，取少量笔记 URL
  3. 逐条打开笔记详情页，采集详情 + 评论
  4. 将结果存储为 JSON 和 CSV 文件
  5. 输出验证报告

运行方式：
    uv run python scripts/verify_note.py [关键词]

示例：
    uv run python scripts/verify_note.py                  # 使用默认关键词
    uv run python scripts/verify_note.py "Python教程"     # 指定关键词

前置条件：
    - 已完成登录（auth_state/state.json 存在）
    - 若未登录请先运行：uv run python scripts/verify_login.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import is_logged_in
from src.browser import BrowserManager
from src.note import fetch_note_details
from src.search import search_notes
from src.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 验证用默认关键词
DEFAULT_KEYWORD = "Python教程"
# 验证时搜索条数（少量即可）
VERIFY_SEARCH_COUNT = 3
# 验证时每条笔记最多评论数
VERIFY_MAX_COMMENTS = 5


async def run(keyword: str) -> bool:
    """执行 Phase 3 笔记详情 + 评论采集验证。

    Returns:
        True 表示验证通过，False 表示失败
    """
    print("\n" + "=" * 60)
    print("  Phase 3 — 笔记详情 + 评论采集验证")
    print("=" * 60)
    print(f"  关键词：{keyword}")
    print(f"  搜索条数：{VERIFY_SEARCH_COUNT}")
    print(f"  每条最多评论：{VERIFY_MAX_COMMENTS}")
    print()

    # ---- 步骤 1: 检查登录态 ----
    auth_state = Path("auth_state/state.json")
    if not auth_state.exists():
        print("  ✗ 未找到登录态文件，请先运行 verify_login.py 完成登录")
        return False

    note_details: list[dict] = []

    async with BrowserManager(headless=False) as bm:
        # ---- 步骤 2: 验证登录态 ----
        print("[1/4] 验证登录态...")
        page = await bm.new_page()
        logged_in = await is_logged_in(page)
        await page.close()

        if not logged_in:
            print("  ✗ 登录态已失效，请重新登录")
            return False
        print("  ✓ 登录态有效\n")

        # ---- 步骤 3: 搜索获取笔记 URL ----
        print(f"[2/4] 搜索关键词：{keyword!r}，目标 {VERIFY_SEARCH_COUNT} 条...")
        search_results = await search_notes(
            bm,
            keyword=keyword,
            max_count=VERIFY_SEARCH_COUNT,
            scroll_pause=1.5,
            scroll_interval=(1.0, 2.5),
        )

        if not search_results:
            print("  ✗ 搜索结果为空，无法继续验证")
            return False

        print(f"  ✓ 搜索到 {len(search_results)} 条笔记\n")

        # ---- 步骤 4: 采集笔记详情 + 评论 ----
        print(f"[3/4] 采集笔记详情 + 评论...")
        note_details = await fetch_note_details(
            bm,
            search_results=search_results,
            max_comments=VERIFY_MAX_COMMENTS,
            delay_range=(2.0, 4.0),
        )

    # ---- 步骤 5: 打印结果摘要 ----
    print(f"\n  共采集到 {len(note_details)} 条笔记详情：")
    print("-" * 70)
    for i, note in enumerate(note_details, start=1):
        title = note.get("title") or "（无标题）"
        author = note.get("author") or "（未知作者）"
        likes = note.get("likes", 0)
        collects = note.get("collects", 0)
        comments = note.get("comments", [])
        content_preview = (note.get("content") or "")[:40]
        tags = note.get("tags", [])

        print(f"  [{i:02d}] {title[:35]}")
        print(f"       作者: {author}  赞:{likes}  藏:{collects}  评论:{len(comments)}条")
        if content_preview:
            print(f"       内容: {content_preview}...")
        if tags:
            print(f"       标签: {', '.join(tags[:5])}")

        # 打印前 3 条评论摘要
        for j, c in enumerate(comments[:3], start=1):
            user = c.get("user_name", "匿名")
            text = (c.get("content") or "")[:30]
            print(f"         评论{j}: [{user}] {text}")

        print()
    print("-" * 70)

    # ---- 步骤 6: 存储结果 ----
    print("[4/4] 存储结果...")
    if note_details:
        storage_config = {
            "output_dir": "data",
            "save_raw_json": True,
            "save_csv": True,
        }
        storage = Storage(storage_config)
        storage.save_note_details(keyword, note_details)

        json_dir = Path("data/raw")
        csv_dir = Path("data/processed")
        json_files = list(json_dir.glob(f"notes_*.json"))
        csv_files = list(csv_dir.glob("*.csv"))
        print(f"  data/raw/       {len(json_files)} 个笔记 JSON 文件")
        print(f"  data/processed/ {len(csv_files)} 个 CSV 文件")

    # ---- 验证结论 ----
    print()
    passed = len(note_details) >= 1
    total_comments = sum(len(n.get("comments", [])) for n in note_details)

    if passed:
        print(f"  ✅ Phase 3 验证通过（笔记 {len(note_details)} 条，评论 {total_comments} 条）")
    else:
        print(f"  ✗ 验证未通过：笔记详情采集失败")
        print("    可能原因：")
        print("    1. 详情页 DOM 选择器已失效（小红书页面改版）")
        print("    2. 页面加载超时或网络异常")
        print("    3. 登录态异常导致被重定向")
        print("    建议：在 headless=False 模式下手动检查页面 DOM 结构")
    print()

    return passed


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYWORD
    success = asyncio.run(run(keyword))
    sys.exit(0 if success else 1)
