"""
浏览器管理模块

职责：
  - 管理 Playwright 浏览器实例的生命周期
  - 集成 stealth 反检测（指纹注入 + stealth 补丁）
  - 管理 browser context 和登录态的保存/加载
  - 提供统一的异步上下文管理器接口

用法：
    async with BrowserManager(headless=False) as bm:
        page = await bm.new_page()
        # ... 采集逻辑
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)

from src.stealth import apply_stealth_to_page, build_stealth, generate_context_options

logger = logging.getLogger(__name__)

AUTH_STATE_PATH = Path("auth_state/state.json")


class BrowserManager:
    """Playwright 浏览器生命周期管理器（异步上下文管理器）。

    每次实例化都会生成新的浏览器指纹，避免指纹固化。
    """

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None

        # 在构建时立即生成指纹，确保同一次会话内指纹一致
        ctx_opts = generate_context_options()
        self._fingerprint = ctx_opts.pop("_fingerprint")
        self._context_options = ctx_opts
        self._stealth = build_stealth(self._fingerprint.navigator.userAgent)

    async def __aenter__(self) -> "BrowserManager":
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
            ],
        )
        logger.info("浏览器启动成功（headless=%s）", self.headless)
        await self._create_context()
        return self

    async def __aexit__(self, *_args) -> None:
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("浏览器已关闭")

    async def _create_context(self) -> None:
        """创建注入指纹的 browser context，并加载已有登录态（若存在）。"""
        if AUTH_STATE_PATH.exists():
            logger.info("检测到登录态文件，加载中：%s", AUTH_STATE_PATH)
            self._context = await self._browser.new_context(
                **self._context_options,
                storage_state=str(AUTH_STATE_PATH),
            )
        else:
            self._context = await self._browser.new_context(**self._context_options)

        # stealth 补丁：对 context 内所有后续打开的页面自动应用
        self._context.on("page", self._on_new_page)

    async def _on_new_page(self, page: Page) -> None:
        """当 context 内打开新页面时自动应用 stealth 补丁。"""
        await apply_stealth_to_page(page, self._stealth)

    async def new_page(self) -> Page:
        """创建并返回一个已应用 stealth 补丁的新页面。"""
        page = await self._context.new_page()
        # on("page") 事件仅对 context.new_page() 触发，此处显式再次应用确保覆盖
        await apply_stealth_to_page(page, self._stealth)
        return page

    async def save_state(self) -> None:
        """将当前 context 的 Cookie / localStorage 保存到文件（持久化登录态）。"""
        AUTH_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        await self._context.storage_state(path=str(AUTH_STATE_PATH))
        logger.info("登录态已保存：%s", AUTH_STATE_PATH)

    @property
    def context(self) -> Optional[BrowserContext]:
        return self._context
