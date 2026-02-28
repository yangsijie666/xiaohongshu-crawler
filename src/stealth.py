"""
反检测配置模块

集成 playwright-stealth 和 browserforge，提供双层反检测能力：
  Layer 1 (环境层) — playwright-stealth：消除 navigator.webdriver 等自动化痕迹
  Layer 2 (指纹层) — browserforge：生成与真实浏览器一致的指纹
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from browserforge.fingerprints import Browser, FingerprintGenerator
from playwright_stealth import Stealth

if TYPE_CHECKING:
    from playwright.async_api import BrowserContext, Page


# Chrome 120+ 的指纹与 Playwright 1.58 使用的 Chromium 145 接近，兼容性最佳
_fingerprint_generator = FingerprintGenerator(
    browser=Browser(name="chrome", min_version=120),
    os="macos",
)


def build_stealth(user_agent: str) -> Stealth:
    """根据指纹 UA 构建 Stealth 实例，覆盖默认的 Win32 平台为 MacIntel。"""
    return Stealth(
        # 保持所有默认的补丁开启
        navigator_platform_override="MacIntel",
        navigator_user_agent_override=user_agent,
        navigator_vendor_override="Google Inc.",
        # 关闭 chrome_runtime 补丁：headed 模式下 Chrome Runtime 本就存在，无需伪装
        chrome_runtime=False,
    )


def generate_context_options() -> dict:
    """生成包含真实浏览器指纹的 browser context 配置。

    每次调用都会随机生成新的指纹，避免指纹固化被关联追踪。

    Returns:
        可直接传入 browser.new_context(**options) 的参数字典。
    """
    fp = _fingerprint_generator.generate()

    return {
        "user_agent": fp.navigator.userAgent,
        "viewport": {
            "width": fp.screen.width,
            "height": fp.screen.height,
        },
        "screen": {
            "width": fp.screen.width,
            "height": fp.screen.height,
        },
        "locale": fp.navigator.language or "zh-CN",
        "timezone_id": "Asia/Shanghai",
        "color_scheme": "light",
        # 返回指纹本身供 Stealth 构建时复用 UA
        "_fingerprint": fp,
    }


async def apply_stealth_to_page(page: "Page", stealth: Stealth) -> None:
    """对单个页面应用 stealth 补丁（每个新页面都需调用）。"""
    await stealth.apply_stealth_async(page)
