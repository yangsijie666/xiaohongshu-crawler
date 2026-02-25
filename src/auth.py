"""
登录与会话管理模块

职责：
  - 检测当前登录态是否有效
  - 引导用户完成手动登录（扫码 / 账号密码）
  - 登录成功后保存 storage_state，供后续采集复用

流程：
    启动 → 访问首页 → 检测登录态
      ├── 有效 → 直接返回
      └── 无效 → 打开登录页 → 等待用户手动登录 → 检测成功 → 保存登录态
"""

from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError

from src.browser import BrowserManager

logger = logging.getLogger(__name__)

REDNOTE_HOME = "https://www.xiaohongshu.com"
REDNOTE_LOGIN = "https://www.xiaohongshu.com/explore"

# 已登录状态的判断依据：页面中存在用户头像元素
# 若小红书改版导致选择器失效，可在此处更新
_LOGGED_IN_SELECTOR = "a[href*='/user/profile']"

# 手动登录等待超时（秒）
LOGIN_WAIT_TIMEOUT = 120


async def is_logged_in(page: Page) -> bool:
    """访问首页，判断当前 context 的登录态是否有效。"""
    try:
        await page.goto(REDNOTE_HOME, wait_until="domcontentloaded", timeout=30_000)
        await page.wait_for_selector(_LOGGED_IN_SELECTOR, timeout=5_000)
        logger.info("登录态有效")
        return True
    except PlaywrightTimeoutError:
        logger.info("未检测到登录态")
        return False


async def wait_for_manual_login(page: Page) -> bool:
    """打开登录页，等待用户手动完成登录。

    Args:
        page: 已应用 stealth 补丁的 Playwright Page 对象

    Returns:
        True 表示登录成功，False 表示超时未登录
    """
    await page.goto(REDNOTE_LOGIN, wait_until="domcontentloaded", timeout=30_000)

    print("\n" + "=" * 60)
    print("请在浏览器中手动完成登录（扫码或账号密码）")
    print(f"等待超时时间：{LOGIN_WAIT_TIMEOUT} 秒")
    print("=" * 60 + "\n")

    try:
        await page.wait_for_selector(
            _LOGGED_IN_SELECTOR,
            timeout=LOGIN_WAIT_TIMEOUT * 1_000,
        )
        logger.info("手动登录成功")
        return True
    except PlaywrightTimeoutError:
        logger.error("等待手动登录超时（%d 秒）", LOGIN_WAIT_TIMEOUT)
        return False


async def ensure_logged_in(bm: BrowserManager) -> bool:
    """确保 BrowserManager 中的 context 处于有效登录态。

    若已有登录态则直接验证复用；否则引导手动登录并保存登录态。

    Args:
        bm: 已初始化的 BrowserManager 实例

    Returns:
        True 表示登录态就绪，False 表示登录失败
    """
    page = await bm.new_page()

    try:
        if await is_logged_in(page):
            return True

        # 登录态无效，引导手动登录
        success = await wait_for_manual_login(page)
        if not success:
            return False

        # 等待页面稳定后保存登录态
        await asyncio.sleep(1)
        await bm.save_state()
        return True
    finally:
        await page.close()
