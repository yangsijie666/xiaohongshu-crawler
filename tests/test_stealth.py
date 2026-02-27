"""
stealth 模块单元测试

测试策略：
  - 使用 unittest.mock.patch 隔离 browserforge / playwright_stealth 外部依赖
  - 覆盖三个公共函数：build_stealth、generate_context_options、apply_stealth_to_page
  - 不依赖真实浏览器，完全在进程内运行
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.stealth import apply_stealth_to_page, build_stealth, generate_context_options


# 合法的 Chrome UA（Stealth 库需要从中解析版本号）
_VALID_CHROME_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


class TestBuildStealth:
    """测试 build_stealth 函数。"""

    def test_returns_stealth_instance(self):
        """应返回 Stealth 实例。"""
        from playwright_stealth import Stealth

        result = build_stealth(_VALID_CHROME_UA)
        assert isinstance(result, Stealth)

    def test_passes_user_agent_to_stealth(self):
        """应将传入的 user_agent 设置到 Stealth 实例。"""
        result = build_stealth(_VALID_CHROME_UA)
        assert result.navigator_user_agent_override == _VALID_CHROME_UA

    def test_sets_platform_to_macintel(self):
        """navigator_platform_override 应为 'MacIntel'。"""
        result = build_stealth(_VALID_CHROME_UA)
        assert result.navigator_platform_override == "MacIntel"

    def test_sets_vendor_to_google(self):
        """navigator_vendor_override 应为 'Google Inc.'。"""
        result = build_stealth(_VALID_CHROME_UA)
        assert result.navigator_vendor_override == "Google Inc."

    def test_chrome_runtime_disabled(self):
        """chrome_runtime 补丁应被禁用（headed 模式兼容性）。"""
        result = build_stealth(_VALID_CHROME_UA)
        assert result.chrome_runtime is False


class TestGenerateContextOptions:
    """测试 generate_context_options 函数。"""

    def _make_mock_fingerprint(
        self,
        ua: str = "Mozilla/5.0 Chrome/120",
        width: int = 1920,
        height: int = 1080,
        language: str = "zh-CN",
    ) -> MagicMock:
        """构造模拟指纹对象。"""
        fp = MagicMock()
        fp.navigator.userAgent = ua
        fp.navigator.language = language
        fp.screen.width = width
        fp.screen.height = height
        return fp

    def test_returns_dict(self):
        """应返回字典类型。"""
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = self._make_mock_fingerprint()
            result = generate_context_options()
        assert isinstance(result, dict)

    def test_contains_user_agent(self):
        """返回字典应包含 user_agent 键。"""
        fp = self._make_mock_fingerprint(ua="MockUA/1.0")
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["user_agent"] == "MockUA/1.0"

    def test_contains_viewport(self):
        """返回字典应包含 viewport（width / height）。"""
        fp = self._make_mock_fingerprint(width=1366, height=768)
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["viewport"]["width"] == 1366
        assert result["viewport"]["height"] == 768

    def test_contains_screen(self):
        """返回字典应包含 screen（width / height）。"""
        fp = self._make_mock_fingerprint(width=2560, height=1600)
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["screen"]["width"] == 2560
        assert result["screen"]["height"] == 1600

    def test_locale_from_fingerprint(self):
        """locale 应来自指纹的 navigator.language。"""
        fp = self._make_mock_fingerprint(language="en-US")
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["locale"] == "en-US"

    def test_locale_falls_back_to_zh_cn_when_none(self):
        """navigator.language 为 None 时 locale 应降级为 'zh-CN'。"""
        fp = self._make_mock_fingerprint()
        fp.navigator.language = None
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["locale"] == "zh-CN"

    def test_timezone_is_shanghai(self):
        """timezone_id 应固定为 'Asia/Shanghai'。"""
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = self._make_mock_fingerprint()
            result = generate_context_options()
        assert result["timezone_id"] == "Asia/Shanghai"

    def test_color_scheme_is_light(self):
        """color_scheme 应固定为 'light'。"""
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = self._make_mock_fingerprint()
            result = generate_context_options()
        assert result["color_scheme"] == "light"

    def test_contains_fingerprint_key(self):
        """返回字典应包含 _fingerprint 键（供 Stealth 构建时复用）。"""
        fp = self._make_mock_fingerprint()
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = fp
            result = generate_context_options()
        assert result["_fingerprint"] is fp

    def test_calls_generate_once_per_invocation(self):
        """每次调用应生成新指纹（调用 generate() 一次）。"""
        with patch("src.stealth._fingerprint_generator") as mock_gen:
            mock_gen.generate.return_value = self._make_mock_fingerprint()
            generate_context_options()
        mock_gen.generate.assert_called_once()


class TestApplyStealthToPage:
    """测试 apply_stealth_to_page 函数。"""

    async def test_calls_apply_stealth_async(self):
        """应调用 stealth.apply_stealth_async(page)。"""
        mock_page = AsyncMock()
        mock_stealth = MagicMock()
        mock_stealth.apply_stealth_async = AsyncMock()

        await apply_stealth_to_page(mock_page, mock_stealth)

        mock_stealth.apply_stealth_async.assert_called_once_with(mock_page)

    async def test_passes_correct_page_to_stealth(self):
        """应将正确的 page 对象传递给 apply_stealth_async。"""
        mock_page = AsyncMock()
        mock_stealth = MagicMock()
        mock_stealth.apply_stealth_async = AsyncMock()

        await apply_stealth_to_page(mock_page, mock_stealth)

        call_args = mock_stealth.apply_stealth_async.call_args
        assert call_args[0][0] is mock_page

    async def test_returns_none(self):
        """函数应返回 None（void 语义）。"""
        mock_page = AsyncMock()
        mock_stealth = MagicMock()
        mock_stealth.apply_stealth_async = AsyncMock(return_value=None)

        result = await apply_stealth_to_page(mock_page, mock_stealth)

        assert result is None
