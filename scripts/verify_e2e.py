"""
Phase 4 端到端验证脚本

验证完整采集流程：关键词 → 搜索 → 详情 → 评论 → 存储

  1. 检查登录态是否就绪
  2. 使用 main.py 的 crawl_keyword() 执行完整单关键词采集
  3. 验证输出文件存在且数据完整性
  4. 输出验证报告

运行方式：
    uv run python scripts/verify_e2e.py [关键词]

示例：
    uv run python scripts/verify_e2e.py                  # 使用默认关键词
    uv run python scripts/verify_e2e.py "Python教程"     # 指定关键词

前置条件：
    - 已完成登录（auth_state/state.json 存在）
    - 若未登录请先运行：uv run python scripts/verify_login.py
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import is_logged_in
from src.browser import BrowserManager
from src.storage import Storage

# 从 main.py 复用 crawl_keyword 逻辑（直接导入）
from main import crawl_keyword

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 验证用默认关键词
DEFAULT_KEYWORD = "Python教程"

# 端到端验证时采用小规模配置，降低耗时
VERIFY_CRAWLER_CFG = {
    "max_notes_per_keyword": 3,   # 仅搜索 3 条笔记
    "max_comments_per_note": 5,   # 每条最多 5 条评论
    "scroll_pause": 1.5,
}

VERIFY_DELAY_CFG = {
    "between_notes": [2.0, 3.0],
    "between_searches": [3.0, 5.0],
    "scroll_interval": [1.0, 2.0],
}

VERIFY_STORAGE_CFG = {
    "output_dir": "data",
    "save_raw_json": True,
    "save_csv": True,
}


def _check_output_files(keyword: str) -> dict:
    """检查本次采集输出的文件，返回验证结果摘要。

    Returns:
        字典包含各类文件的存在状态和统计信息
    """
    data_dir = Path("data")
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"

    # 安全化关键词（与 storage.py 逻辑一致）
    import re
    safe_kw = re.sub(r'[\\/:*?"<>|\s]', "_", keyword)
    safe_kw = re.sub(r"_+", "_", safe_kw).strip("_") or "unnamed"

    result: dict = {
        "search_json": [],
        "notes_json": [],
        "search_csv": None,
        "notes_csv": None,
        "comments_csv": None,
    }

    if raw_dir.exists():
        # 搜索结果 JSON
        result["search_json"] = sorted(raw_dir.glob(f"{safe_kw}_*.json"))
        # 笔记详情 JSON
        result["notes_json"] = sorted(raw_dir.glob(f"notes_{safe_kw}_*.json"))

    if processed_dir.exists():
        search_csv = processed_dir / f"search_results_{safe_kw}.csv"
        notes_csv = processed_dir / f"notes_{safe_kw}.csv"
        comments_csv = processed_dir / f"comments_{safe_kw}.csv"
        result["search_csv"] = search_csv if search_csv.exists() else None
        result["notes_csv"] = notes_csv if notes_csv.exists() else None
        result["comments_csv"] = comments_csv if comments_csv.exists() else None

    return result


def _count_json_records(json_path: Path, key: str) -> int:
    """从 JSON 文件读取指定 key 的数组长度。"""
    try:
        with open(json_path, encoding="utf-8") as f:
            data = json.load(f)
        items = data.get(key, [])
        return len(items)
    except Exception:
        return -1


def _count_csv_rows(csv_path: Path) -> int:
    """统计 CSV 文件的数据行数（不含表头）。"""
    try:
        lines = csv_path.read_text(encoding="utf-8-sig").splitlines()
        return max(0, len(lines) - 1)  # 减去表头
    except Exception:
        return -1


async def run(keyword: str) -> bool:
    """执行 Phase 4 端到端验证。

    Returns:
        True 表示验证通过，False 表示失败
    """
    print("\n" + "=" * 60)
    print("  Phase 4 — 端到端集成验证")
    print("=" * 60)
    print(f"  关键词：{keyword}")
    print(f"  采集规模：{VERIFY_CRAWLER_CFG['max_notes_per_keyword']} 条笔记，"
          f"每条最多 {VERIFY_CRAWLER_CFG['max_comments_per_note']} 条评论")
    print()

    # ---- 步骤 1: 检查登录态文件 ----
    auth_state = Path("auth_state/state.json")
    if not auth_state.exists():
        print("  ✗ 未找到登录态文件，请先运行 verify_login.py 完成登录")
        return False

    crawl_success = False

    async with BrowserManager(headless=False) as bm:
        # ---- 步骤 2: 验证登录态有效性 ----
        print("[1/3] 验证登录态...")
        page = await bm.new_page()
        logged_in = await is_logged_in(page)
        await page.close()

        if not logged_in:
            print("  ✗ 登录态已失效，请重新登录（verify_login.py）")
            return False
        print("  ✓ 登录态有效\n")

        # ---- 步骤 3: 执行完整采集流程 ----
        print(f"[2/3] 执行端到端采集流程（关键词：{keyword!r}）...")
        storage = Storage(VERIFY_STORAGE_CFG)
        try:
            await crawl_keyword(
                bm,
                keyword=keyword,
                crawler_cfg=VERIFY_CRAWLER_CFG,
                delay_cfg=VERIFY_DELAY_CFG,
                storage=storage,
            )
            crawl_success = True
            print("  ✓ 采集流程完成\n")
        except Exception as e:
            logger.error("采集流程异常：%s", e, exc_info=True)
            print(f"  ✗ 采集流程异常：{e}")
            return False

    if not crawl_success:
        return False

    # ---- 步骤 4: 验证输出文件 ----
    print("[3/3] 验证输出文件...")
    files = _check_output_files(keyword)

    passed = True
    checks: list[tuple[str, bool, str]] = []

    # 检查搜索结果 JSON
    if files["search_json"]:
        latest_json = files["search_json"][-1]
        count = _count_json_records(latest_json, "results")
        ok = count >= 1
        checks.append((
            f"搜索结果 JSON（{latest_json.name}）",
            ok,
            f"{count} 条记录" if count >= 0 else "读取失败",
        ))
    else:
        checks.append(("搜索结果 JSON", False, "文件不存在"))
        passed = False

    # 检查笔记详情 JSON
    if files["notes_json"]:
        latest_json = files["notes_json"][-1]
        count = _count_json_records(latest_json, "notes")
        ok = count >= 1
        checks.append((
            f"笔记详情 JSON（{latest_json.name}）",
            ok,
            f"{count} 条记录" if count >= 0 else "读取失败",
        ))
        if not ok:
            passed = False
    else:
        checks.append(("笔记详情 JSON", False, "文件不存在"))
        passed = False

    # 检查搜索结果 CSV
    if files["search_csv"]:
        count = _count_csv_rows(files["search_csv"])
        ok = count >= 1
        checks.append((f"搜索结果 CSV（{files['search_csv'].name}）", ok, f"{count} 行"))
        if not ok:
            passed = False
    else:
        checks.append(("搜索结果 CSV", False, "文件不存在"))
        passed = False

    # 检查笔记详情 CSV
    if files["notes_csv"]:
        count = _count_csv_rows(files["notes_csv"])
        ok = count >= 1
        checks.append((f"笔记详情 CSV（{files['notes_csv'].name}）", ok, f"{count} 行"))
        if not ok:
            passed = False
    else:
        checks.append(("笔记详情 CSV", False, "文件不存在"))
        passed = False

    # 检查评论 CSV（有评论才要求存在）
    if files["comments_csv"]:
        count = _count_csv_rows(files["comments_csv"])
        checks.append((
            f"评论 CSV（{files['comments_csv'].name}）",
            count >= 0,
            f"{count} 行",
        ))
    else:
        # 评论 CSV 不存在可能是笔记无评论，记录但不计失败
        checks.append(("评论 CSV", True, "无评论数据（笔记可能无评论）"))

    # 打印检查结果
    print()
    for name, ok, detail in checks:
        mark = "✓" if ok else "✗"
        print(f"  {mark} {name}：{detail}")

    # ---- 验证结论 ----
    print()
    if passed:
        print(f"  ✅ Phase 4 端到端验证通过")
        print(f"     关键词 [{keyword}] 完整采集流程运行正常")
        print(f"     数据文件已输出到 data/ 目录")
    else:
        print(f"  ✗ Phase 4 端到端验证未通过")
        print("    请检查上方失败项的详细输出日志")
        print("    建议：在 headless=False 模式下观察浏览器行为")
    print()

    return passed


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYWORD
    success = asyncio.run(run(keyword))
    sys.exit(0 if success else 1)
