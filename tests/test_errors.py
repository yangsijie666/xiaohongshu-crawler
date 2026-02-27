"""
统一错误格式模块测试（Phase D — D3）

测试策略：
  - 验证 CrawlerError 不可变性（frozen dataclass）
  - 验证 to_dict() 输出格式与字段完整性
  - 验证预定义错误工厂函数的字段值
  - 覆盖所有错误码常量
"""

from __future__ import annotations

import pytest

from src.errors import (
    CrawlerError,
    browser_crashed_error,
    browser_not_running_error,
    crawl_failed_error,
    invalid_input_error,
    login_expired_error,
    timeout_error,
)


class TestCrawlerErrorDataclass:
    """测试 CrawlerError 数据结构。"""

    def test_fields_are_set(self):
        """应正确存储 code / message / action 三个字段。"""
        err = CrawlerError(code="TEST", message="测试消息", action="测试操作")
        assert err.code == "TEST"
        assert err.message == "测试消息"
        assert err.action == "测试操作"

    def test_frozen_immutability(self):
        """frozen=True 应防止字段被修改。"""
        err = CrawlerError(code="TEST", message="msg", action="act")
        with pytest.raises(AttributeError):
            err.code = "CHANGED"

    def test_to_dict_format(self):
        """to_dict() 应返回标准错误字典格式。"""
        err = CrawlerError(code="ERR_CODE", message="出错了", action="请重试")
        result = err.to_dict()

        assert result == {
            "error": True,
            "code": "ERR_CODE",
            "message": "出错了",
            "action": "请重试",
        }

    def test_to_dict_always_has_error_true(self):
        """to_dict() 的 error 字段始终为 True。"""
        err = CrawlerError(code="X", message="m", action="a")
        assert err.to_dict()["error"] is True

    def test_to_dict_returns_new_dict_each_call(self):
        """每次调用 to_dict() 应返回新字典（不可变性保证）。"""
        err = CrawlerError(code="X", message="m", action="a")
        d1 = err.to_dict()
        d2 = err.to_dict()
        assert d1 == d2
        assert d1 is not d2


class TestPredefinedErrors:
    """测试预定义错误工厂函数。"""

    def test_browser_not_running_error(self):
        """浏览器未启动错误应包含正确的 code 和 action。"""
        err = browser_not_running_error()
        d = err.to_dict()
        assert d["code"] == "BROWSER_NOT_RUNNING"
        assert d["error"] is True
        assert "action" in d
        assert len(d["message"]) > 0

    def test_browser_crashed_error(self):
        """浏览器崩溃错误应包含正确的 code。"""
        err = browser_crashed_error()
        d = err.to_dict()
        assert d["code"] == "BROWSER_CRASHED"
        assert "恢复" in d["action"] or "重启" in d["action"]

    def test_login_expired_error(self):
        """登录态失效错误应包含正确的 code 和登录指引。"""
        err = login_expired_error()
        d = err.to_dict()
        assert d["code"] == "LOGIN_EXPIRED"
        assert "verify_login" in d["action"]

    def test_timeout_error_with_tool_name(self):
        """超时错误应包含工具名称和超时时长。"""
        err = timeout_error(tool_name="search_notes", timeout_seconds=120)
        d = err.to_dict()
        assert d["code"] == "TIMEOUT"
        assert "search_notes" in d["message"]
        assert "120" in d["message"]

    def test_timeout_error_custom_values(self):
        """超时错误应正确填入自定义参数。"""
        err = timeout_error(tool_name="crawl_keyword", timeout_seconds=600)
        d = err.to_dict()
        assert "crawl_keyword" in d["message"]
        assert "600" in d["message"]

    def test_invalid_input_error_with_field(self):
        """无效输入错误应包含字段名和具体说明。"""
        err = invalid_input_error(field="keyword", reason="不能为空")
        d = err.to_dict()
        assert d["code"] == "INVALID_INPUT"
        assert "keyword" in d["message"]
        assert "不能为空" in d["message"]

    def test_crawl_failed_error_with_detail(self):
        """采集失败错误应包含具体失败信息。"""
        err = crawl_failed_error(detail="URL 无效或页面无法加载")
        d = err.to_dict()
        assert d["code"] == "CRAWL_FAILED"
        assert "URL" in d["message"]
