"""
统一错误格式模块（Phase D — D3）

职责：
  - 定义 MCP 工具返回的统一错误数据结构
  - 提供预定义错误工厂函数，确保错误码和消息风格一致
  - 所有 MCP 工具错误均通过此模块构建，方便 AI 助手解析和处理

错误字典格式：
  {
      "error": True,       # 标识为错误响应
      "code": str,         # 机器可读的错误码（大写下划线）
      "message": str,      # 人类可读的错误描述
      "action": str        # 建议的修复操作
  }

错误码列表：
  - BROWSER_NOT_RUNNING: 浏览器未启动
  - BROWSER_CRASHED: 浏览器崩溃且自动恢复失败
  - LOGIN_EXPIRED: 登录态已失效
  - TIMEOUT: 操作超时
  - INVALID_INPUT: 输入参数无效
  - CRAWL_FAILED: 采集操作失败
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrawlerError:
    """MCP 工具统一错误结构（不可变）。

    Attributes:
        code: 机器可读的错误码（如 BROWSER_NOT_RUNNING）
        message: 人类可读的错误描述
        action: 建议用户或 AI 执行的修复操作
    """

    code: str
    message: str
    action: str

    def to_dict(self) -> dict:
        """转换为标准错误字典，供 MCP 工具返回。"""
        return {
            "error": True,
            "code": self.code,
            "message": self.message,
            "action": self.action,
        }


# ============================================================
# 预定义错误工厂函数
# ============================================================


def browser_not_running_error() -> CrawlerError:
    """浏览器未启动时的错误。"""
    return CrawlerError(
        code="BROWSER_NOT_RUNNING",
        message="浏览器未启动。请确保 MCP 服务正常运行后重试。",
        action="请重启 MCP 服务，或检查 Playwright 是否正确安装。",
    )


def browser_crashed_error() -> CrawlerError:
    """浏览器崩溃且自动恢复失败时的错误。"""
    return CrawlerError(
        code="BROWSER_CRASHED",
        message="浏览器已崩溃且自动恢复失败。",
        action="请重启 MCP 服务以恢复浏览器。",
    )


def login_expired_error() -> CrawlerError:
    """登录态失效时的错误。"""
    return CrawlerError(
        code="LOGIN_EXPIRED",
        message="小红书登录态已失效，需要重新登录。",
        action=(
            "请在终端运行 `uv run python scripts/verify_login.py` "
            "完成扫码登录，然后重启 MCP 服务。"
        ),
    )


def timeout_error(tool_name: str, timeout_seconds: int) -> CrawlerError:
    """操作超时时的错误。

    Args:
        tool_name: 超时的工具名称
        timeout_seconds: 超时时长（秒）
    """
    return CrawlerError(
        code="TIMEOUT",
        message=f"{tool_name} 操作超时（{timeout_seconds} 秒）。",
        action="请稍后重试，或减少采集数量（如 max_count / max_notes）。",
    )


def invalid_input_error(field: str, reason: str) -> CrawlerError:
    """输入参数无效时的错误。

    Args:
        field: 无效的参数名
        reason: 无效原因
    """
    return CrawlerError(
        code="INVALID_INPUT",
        message=f"参数 {field} 无效：{reason}",
        action=f"请检查 {field} 参数后重试。",
    )


def crawl_failed_error(detail: str) -> CrawlerError:
    """采集操作失败时的错误。

    Args:
        detail: 失败的具体原因
    """
    return CrawlerError(
        code="CRAWL_FAILED",
        message=f"采集失败：{detail}",
        action="请检查 URL 是否有效，或稍后重试。",
    )
