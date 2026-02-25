"""
登录态验证脚本

验证两个场景：
  场景 A — 首次登录：auth_state/state.json 不存在时引导手动登录并保存登录态
  场景 B — 复用登录态：auth_state/state.json 存在时直接加载并验证是否仍然有效

运行方式：
    uv run python scripts/verify_login.py

若需要强制重新登录（清除已有登录态）：
    rm auth_state/state.json
    uv run python scripts/verify_login.py
"""

import asyncio
import datetime
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.auth import _LOGGED_IN_SELECTOR, is_logged_in, wait_for_manual_login
from src.browser import AUTH_STATE_PATH, BrowserManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    print("\n" + "=" * 60)
    print("  登录态验证")
    print("=" * 60)

    state_exists = AUTH_STATE_PATH.exists()

    if state_exists:
        mtime = AUTH_STATE_PATH.stat().st_mtime
        ts = datetime.datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M:%S")
        print(f"  检测到已有登录态文件：{AUTH_STATE_PATH}")
        print(f"  文件修改时间：{ts}")
        print(f"\n  场景 B — 验证登录态复用\n")
    else:
        print(f"  未找到登录态文件：{AUTH_STATE_PATH}")
        print(f"\n  场景 A — 引导手动首次登录\n")

    async with BrowserManager(headless=False) as bm:
        page = await bm.new_page()

        if state_exists:
            # 场景 B：验证已有登录态是否仍然有效
            logged_in = await is_logged_in(page)
            if logged_in:
                print("\n  ✓ 登录态复用成功，无需重新登录")
                print(f"    当前页面：{page.url}")

                # 尝试提取用户主页路径以进一步确认
                try:
                    user_el = await page.query_selector(_LOGGED_IN_SELECTOR)
                    href = await user_el.get_attribute("href") if user_el else None
                    if href:
                        print(f"    用户主页路径：{href}")
                except Exception:
                    pass
            else:
                print("\n  ✗ 登录态已失效（Cookie 过期或账号变更）")
                print("    请删除 auth_state/state.json 后重新运行此脚本进行手动登录")

        else:
            # 场景 A：引导手动登录
            success = await wait_for_manual_login(page)
            if success:
                await asyncio.sleep(1)
                await bm.save_state()
                print(f"\n  ✓ 首次登录成功")
                print(f"    登录态已保存至：{AUTH_STATE_PATH}")
                print(f"    下次运行将自动复用，无需再次登录")
            else:
                print(f"\n  ✗ 登录超时，未完成登录")

        await page.close()

    print()


if __name__ == "__main__":
    asyncio.run(run())
