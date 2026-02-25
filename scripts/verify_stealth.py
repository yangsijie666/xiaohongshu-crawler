"""
反检测验证脚本

访问 bot.sannysoft.com 检测站点，提取各项测试结果并打印汇总报告。
同时截图保存至 data/verify_stealth.png，便于人工核查。

运行方式：
    uv run python scripts/verify_stealth.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# 将项目根目录加入 sys.path，以便直接运行此脚本
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.browser import BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

TEST_URL = "https://bot.sannysoft.com"
SCREENSHOT_PATH = Path("data/verify_stealth.png")

# bot.sannysoft.com 各测试项的 DOM 结构：
#   <tr> <td>测试名</td> <td class="result passed|result failed">结果文本</td> </tr>
# class 格式为 "result passed" 或 "result failed"（含空格的复合 class）
_RESULTS_SELECTOR = "tr:has(td.result)"


async def run() -> None:
    Path("data").mkdir(exist_ok=True)

    print("\n" + "=" * 60)
    print("  反检测验证 — bot.sannysoft.com")
    print("=" * 60)
    print(f"目标地址：{TEST_URL}")
    print(f"截图保存：{SCREENSHOT_PATH}\n")

    async with BrowserManager(headless=False) as bm:
        page = await bm.new_page()

        logger.info("正在访问 %s …", TEST_URL)
        # 使用 load 避免 networkidle 在该站点超时
        await page.goto(TEST_URL, wait_until="load", timeout=30_000)

        # 等待页面内 JS 检测脚本全部执行完毕（该页面通过 JS 动态填充结果）
        await asyncio.sleep(5)

        # 截图
        await page.screenshot(path=str(SCREENSHOT_PATH), full_page=True)
        logger.info("截图已保存：%s", SCREENSHOT_PATH)

        # 提取测试结果
        rows = await page.query_selector_all(_RESULTS_SELECTOR)
        results: list[dict] = []

        for row in rows:
            cells = await row.query_selector_all("td")
            if len(cells) < 2:
                continue

            name = (await cells[0].inner_text()).strip()
            value_el = cells[1]
            class_attr = (await value_el.get_attribute("class") or "").lower()
            value = (await value_el.inner_text()).strip()

            if "passed" in class_attr:
                status = "PASS"
            elif "failed" in class_attr:
                status = "FAIL"
            else:
                status = "INFO"

            results.append({"name": name, "value": value, "status": status})

        # 打印报告
        _print_report(results)


def _print_report(results: list[dict]) -> None:
    if not results:
        print("\n[!] 未能提取到测试结果，请查看截图手动核查\n")
        return

    passed = [r for r in results if r["status"] == "PASS"]
    failed = [r for r in results if r["status"] == "FAIL"]
    info   = [r for r in results if r["status"] == "INFO"]

    print("\n─── 详细结果 " + "─" * 46)
    col_w = max(len(r["name"]) for r in results) + 2

    for r in results:
        icon = {"PASS": "✓", "FAIL": "✗", "INFO": "·"}[r["status"]]
        color = {"PASS": "\033[32m", "FAIL": "\033[31m", "INFO": "\033[0m"}[r["status"]]
        reset = "\033[0m"
        print(f"  {color}{icon}{reset}  {r['name']:<{col_w}} {r['value']}")

    print("\n─── 汇总 " + "─" * 50)
    print(f"  通过：{len(passed)}  失败：{len(failed)}  信息：{len(info)}")

    if failed:
        print("\n  ⚠ 以下项目未通过，可能被检测为自动化工具：")
        for r in failed:
            print(f"    - {r['name']}: {r['value']}")
    else:
        print("\n  所有检测项均通过，stealth 配置有效")

    print()


if __name__ == "__main__":
    asyncio.run(run())
