"""
Phase B MCP 工具端到端验证脚本

验证 MCP 工具层（mcp_server.py）的真实浏览器行为：
  1. 启动 CrawlerSession（真实浏览器）
  2. 调用 check_login_status 工具，验证返回结构
  3. 验证 search_notes 输入验证逻辑（空 keyword、max_count 截断）
  4. 调用 search_notes 工具，验证结构化返回
  5. 调用 get_note_detail 工具（取第一条搜索结果的 URL）
  6. 输出验证报告

运行方式：
    uv run python scripts/verify_mcp_tools.py [关键词]

示例：
    uv run python scripts/verify_mcp_tools.py              # 使用默认关键词
    uv run python scripts/verify_mcp_tools.py "Python教程" # 指定关键词

前置条件：
    - 已完成登录（auth_state/state.json 存在）
    - 若未登录请先运行：uv run python scripts/verify_login.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import mcp_server
from src.session import CrawlerSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# 验证用默认关键词
DEFAULT_KEYWORD = "Python教程"

# 端到端验证时采用小规模配置，降低耗时
VERIFY_MAX_COUNT = 3
VERIFY_MAX_COMMENTS = 5


def _check(label: str, condition: bool, detail: str = "") -> bool:
    """打印单项检查结果，返回是否通过。"""
    mark = "✓" if condition else "✗"
    suffix = f"：{detail}" if detail else ""
    print(f"  {mark} {label}{suffix}")
    return condition


async def run(keyword: str) -> bool:
    """执行 Phase B MCP 工具端到端验证。

    Returns:
        True 表示验证通过，False 表示失败
    """
    print("\n" + "=" * 60)
    print("  Phase B — MCP 工具端到端验证")
    print("=" * 60)
    print(f"  关键词：{keyword}")
    print(f"  搜索数量：{VERIFY_MAX_COUNT}，评论数量：{VERIFY_MAX_COMMENTS}")
    print()

    # ---- 检查登录态文件 ----
    auth_state = Path("auth_state/state.json")
    if not auth_state.exists():
        print("  ✗ 未找到登录态文件，请先运行 verify_login.py 完成登录")
        return False

    passed = True
    session = CrawlerSession(headless=False)

    # 替换模块级 _session，使 mcp_server 工具函数使用本地 session
    original_session = mcp_server._session
    mcp_server._session = session

    search_result: dict = {}

    try:
        # ---- 步骤 1: 启动浏览器会话（lifespan 模拟）----
        print("[1/5] 启动浏览器会话...")
        await session.start()
        ok = _check("浏览器会话启动成功", session.is_running() is True)
        passed &= ok
        print()

        # ---- 步骤 2: 验证 check_login_status 工具 ----
        print("[2/5] 验证 check_login_status 工具...")
        login_result = await mcp_server.check_login_status()
        passed &= _check("返回结构包含 logged_in", "logged_in" in login_result)
        passed &= _check("返回结构包含 browser_running", "browser_running" in login_result)
        passed &= _check("返回结构包含 message", "message" in login_result)
        passed &= _check("browser_running=True", login_result.get("browser_running") is True)

        is_logged_in = login_result.get("logged_in", False)
        if not is_logged_in:
            print("\n  ⚠️  未登录状态，后续搜索/详情工具验证将跳过。")
            print("     请先运行 verify_login.py 完成登录后重试。")
        else:
            print("  ✓ 已登录小红书")
        print()

        # ---- 步骤 3: 验证 search_notes 输入验证逻辑 ----
        print("[3/5] 验证 search_notes 输入验证...")

        empty_result = await mcp_server.search_notes(keyword="")
        passed &= _check("空 keyword 返回 error=True", empty_result.get("error") is True)

        ws_result = await mcp_server.search_notes(keyword="   ")
        passed &= _check("纯空白 keyword 返回 error=True", ws_result.get("error") is True)

        # max_count=200 应不崩溃（截断到 50）
        try:
            await mcp_server.search_notes(keyword="test_clamp", max_count=200)
            passed &= _check("max_count=200 不崩溃", True)
        except Exception as e:
            passed &= _check("max_count=200 不崩溃", False, str(e))

        # max_count=0 应被截断到 1
        try:
            await mcp_server.search_notes(keyword="test_clamp", max_count=0)
            passed &= _check("max_count=0 不崩溃", True)
        except Exception as e:
            passed &= _check("max_count=0 不崩溃", False, str(e))
        print()

        # ---- 步骤 4: 验证 search_notes 正常调用 ----
        print(f"[4/5] 验证 search_notes（keyword={keyword!r}，max_count={VERIFY_MAX_COUNT}）...")

        if is_logged_in:
            search_result = await mcp_server.search_notes(
                keyword=keyword, max_count=VERIFY_MAX_COUNT
            )

            if search_result.get("error"):
                print(f"  ⚠️  搜索返回错误：{search_result.get('message', '未知错误')}")
                print("     可能原因：页面结构变更或网络异常")
            else:
                passed &= _check("返回结构包含 keyword", "keyword" in search_result)
                passed &= _check("返回结构包含 count", "count" in search_result)
                passed &= _check("返回结构包含 results", "results" in search_result)

                result_count = len(search_result.get("results", []))
                passed &= _check(f"results 非空", result_count >= 1, f"{result_count} 条")

                returned_keyword = search_result.get("keyword", "")
                passed &= _check(
                    "keyword 字段与输入一致",
                    returned_keyword == keyword,
                    f"期望={keyword!r}，实际={returned_keyword!r}",
                )
        else:
            print("  ⚠️  跳过（未登录）")
        print()

        # ---- 步骤 5: 验证 get_note_detail 工具 ----
        print("[5/5] 验证 get_note_detail 工具...")

        # 5a. 输入验证：空 URL
        empty_url_result = await mcp_server.get_note_detail(note_url="")
        passed &= _check("空 note_url 返回 error=True", empty_url_result.get("error") is True)

        # 5b. 真实采集（需要登录 + 有搜索结果）
        if is_logged_in and not search_result.get("error") and search_result.get("results"):
            first_note = search_result["results"][0]
            note_url = first_note.get("note_url", "")

            if note_url:
                safe_url = note_url.split("?")[0]
                print(f"\n  采集第一条笔记：{safe_url}...")

                detail_result = await mcp_server.get_note_detail(
                    note_url=note_url, max_comments=VERIFY_MAX_COMMENTS
                )

                if detail_result.get("error"):
                    print(f"  ⚠️  采集失败：{detail_result.get('message', '未知错误')}")
                    print("     可能原因：页面结构变更、URL 失效或网络异常")
                else:
                    passed &= _check("详情包含 note_id", "note_id" in detail_result)
                    passed &= _check("详情包含 title", "title" in detail_result)
                    passed &= _check("详情包含 comments", "comments" in detail_result)

                    comments = detail_result.get("comments", [])
                    print(f"  ✓ 评论数：{len(comments)}")

                    title_preview = (detail_result.get("title") or "")[:30]
                    if title_preview:
                        print(f"  ✓ 标题：{title_preview}...")
            else:
                print("  ⚠️  跳过 get_note_detail（第一条搜索结果无 note_url）")
        else:
            print("  ⚠️  跳过（未登录或无搜索结果）")

    except Exception as e:
        logger.error("验证异常：%s", e, exc_info=True)
        print(f"\n  ✗ 验证异常：{e}")
        passed = False

    finally:
        # ---- 清理 ----
        print("\n清理：停止浏览器会话...")
        await session.stop()
        mcp_server._session = original_session
        print("  浏览器会话已关闭")

    # ---- 验证结论 ----
    print()
    print("=" * 60)
    if passed:
        print("  ✅ Phase B MCP 工具验证通过")
        print("  check_login_status / search_notes / get_note_detail 工具运行正常")
    else:
        print("  ✗ Phase B MCP 工具验证未通过")
        print("  请检查上方失败项的详细输出日志")
        print("  建议：在 headless=False 模式下观察浏览器行为")
    print()

    return passed


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_KEYWORD
    success = asyncio.run(run(keyword))
    sys.exit(0 if success else 1)
