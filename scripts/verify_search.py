"""
Phase 2 搜索采集验证脚本

验证搜索采集的完整链路：
  1. 复用已有登录态（须先完成登录，参考 verify_login.py）
  2. 按关键词执行搜索，提取笔记摘要列表
  3. 将结果存储为 JSON 和 CSV 文件
  4. 输出验证报告

运行方式：
    uv run python scripts/verify_search.py [关键词]

示例：
    uv run python scripts/verify_search.py                  # 使用默认关键词
    uv run python scripts/verify_search.py "Python教程"     # 指定关键词

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
from src.search import search_notes
from src.storage import Storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 验证用默认关键词（可通过命令行参数覆盖）
DEFAULT_KEYWORD = "Python教程"
# 验证时采集条数（少量即可）
VERIFY_MAX_COUNT = 5

# 最小预期条数（低于此数视为异常）
MIN_EXPECTED_COUNT = 1


async def run(keyword: str) -> bool:
    """执行 Phase 2 搜索采集验证。

    Returns:
        True 表示验证通过，False 表示失败
    """
    print("\n" + "=" * 60)
    print("  Phase 2 — 搜索采集验证")
    print("=" * 60)
    print(f"  关键词：{keyword}")
    print(f"  目标条数：{VERIFY_MAX_COUNT}")
    print()

    # ---- 步骤 1: 检查登录态 ----
    auth_state = Path("auth_state/state.json")
    if not auth_state.exists():
        print("  ✗ 未找到登录态文件，请先运行 verify_login.py 完成登录")
        return False

    # ---- 步骤 2: 执行搜索采集 ----
    results: list[dict] = []
    async with BrowserManager(headless=False) as bm:
        print("[1/3] 验证登录态...")
        page = await bm.new_page()
        logged_in = await is_logged_in(page)
        await page.close()

        if not logged_in:
            print("  ✗ 登录态已失效，请重新登录")
            return False
        print("  ✓ 登录态有效\n")

        print(f"[2/3] 搜索关键词：{keyword!r}，目标 {VERIFY_MAX_COUNT} 条...")
        results = await search_notes(
            bm,
            keyword=keyword,
            max_count=VERIFY_MAX_COUNT,
            scroll_pause=1.5,
            scroll_interval=(1.0, 2.5),
        )

    # ---- 步骤 3: 打印结果摘要 ----
    print(f"\n  共采集到 {len(results)} 条笔记：")
    print("-" * 60)
    for i, note in enumerate(results, start=1):
        title = note.get("title") or "（无标题）"
        author = note.get("author") or "（未知作者）"
        likes = note.get("likes", 0)
        note_type = note.get("note_type", "image")
        note_id = note.get("note_id", "")
        print(f"  [{i:02d}] {title[:30]:<30}  作者:{author:<12}  赞:{likes:<6}  类型:{note_type}  ID:{note_id}")
    print("-" * 60)

    # ---- 步骤 4: 存储结果 ----
    print(f"\n[3/3] 存储结果...")
    if results:
        storage_config = {
            "output_dir": "data",
            "save_raw_json": True,
            "save_csv": True,
        }
        storage = Storage(storage_config)
        storage.save_search_results(keyword, results)

        json_dir = Path("data/raw")
        csv_dir = Path("data/processed")
        json_files = list(json_dir.glob(f"*{keyword[:4]}*.json"))
        csv_files = list(csv_dir.glob("*.csv"))
        print(f"  data/raw/       {len(json_files)} 个 JSON 文件")
        print(f"  data/processed/ {len(csv_files)} 个 CSV 文件")

    # ---- 验证结论 ----
    print()
    passed = len(results) >= MIN_EXPECTED_COUNT
    if passed:
        print(f"  ✅ Phase 2 搜索采集验证通过（采集 {len(results)} 条）")
    else:
        print(f"  ✗ 验证未通过：采集结果不足（期望 >= {MIN_EXPECTED_COUNT} 条，实际 {len(results)} 条）")
        print("    可能原因：")
        print("    1. 卡片选择器已失效（小红书页面改版）")
        print("    2. 网络问题导致页面未正常加载")
        print("    3. 登录态异常导致被重定向")
        print("    建议：在 headless=False 模式下手动检查页面 DOM 结构")
    print()

    return passed


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYWORD
    success = asyncio.run(run(keyword))
    sys.exit(0 if success else 1)
