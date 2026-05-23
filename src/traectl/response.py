#!/usr/bin/env python3
"""标准化 JSON 响应外壳——符合 agentic-cli-design 的响应 envelope。"""

import json
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

# ── 退出码 ────────────────────────────────────────────────────
EXIT_SUCCESS = 0          # 操作成功
EXIT_GENERAL_ERROR = 1    # 未指定的一般错误
EXIT_USAGE_ERROR = 2      # 无效参数/用法
EXIT_AUTH_ERROR = 3       # 认证/权限错误
EXIT_RETRYABLE = 4        # 可重试错误（限流、网络瞬断）
EXIT_CONFIRMATION_REQUIRED = 10  # 需要确认（高风险操作）


# ── 统一返回格式 ──────────────────────────────────────────────

class StandardResponse:
    """统一方法返回格式。所有 controller 方法返回此对象。"""
    def __init__(self, result=None, message="", code=0, exit_code=0):
        self.result = result
        self.message = message
        self.code = code
        self.exit_code = exit_code

    def __str__(self):
        return self.message

    def __repr__(self):
        return f"StandardResponse(code={self.code}, exit_code={self.exit_code}, message={self.message!r})"

    def to_dict(self):
        return {"result": self.result, "message": self.message, "code": self.code, "exit_code": self.exit_code}

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ── 响应外壳 ──────────────────────────────────────────────────

@dataclass
class JsonResponse:
    """标准化 JSON 响应外壳。所有 CLI 命令输出用此包装。"""
    schemaVersion: int = 1
    type: str = ""
    ok: bool = True
    data: Any = None
    error: Optional[dict] = None
    dryRun: Optional[bool] = None
    plan: Optional[dict] = None
    exit_code: int = EXIT_SUCCESS
    risk: Optional[str] = None
    confirmation_required: Optional[bool] = None
    hint: Optional[str] = None
    metadata: dict = field(default_factory=lambda: {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })

    def to_json(self) -> str:
        """序列化为 JSON 字符串（仅含非 None 字段）。"""
        raw = {"schemaVersion": self.schemaVersion, "type": self.type, "ok": self.ok}
        if self.data is not None:
            raw["data"] = self.data
        if self.error is not None:
            raw["error"] = self.error
        if self.dryRun is not None:
            raw["dryRun"] = self.dryRun
        if self.plan is not None:
            raw["plan"] = self.plan
        if self.exit_code != EXIT_SUCCESS:
            raw["exit_code"] = self.exit_code
        if self.risk is not None:
            raw["risk"] = self.risk
        if self.confirmation_required is not None:
            raw["confirmation_required"] = self.confirmation_required
        if self.hint is not None:
            raw["hint"] = self.hint
        raw["metadata"] = self.metadata
        return json.dumps(raw, ensure_ascii=False, indent=2)


def ok(data: Any, type_: str = "", exit_code: int = EXIT_SUCCESS, risk: str = "low", confirmation_required: bool = False, hint: str = "") -> str:
    """创建成功响应并设置退出码。"""
    if confirmation_required:
        exit_code = EXIT_CONFIRMATION_REQUIRED
        risk = "high"
    resp = JsonResponse(
        ok=True, data=data, type=type_, exit_code=exit_code,
        risk=risk if risk != "low" else None,
        confirmation_required=confirmation_required if confirmation_required else None,
        hint=hint if hint else None,
    )
    _tag_exit_code(exit_code)
    return resp.to_json()


def error(
    code: str,
    message: str,
    details: Optional[dict] = None,
    retryable: bool = False,
    exit_code: Optional[int] = None,
    type_: str = "",
    risk: str = "low",
    confirmation_required: bool = False,
    hint: str = "",
) -> str:
    """创建错误响应并自动设置退出码。"""
    err = {"code": code, "message": message}
    if details:
        err["details"] = details
    if retryable:
        err["retryable"] = True

    if confirmation_required:
        exit_code = EXIT_CONFIRMATION_REQUIRED

    if exit_code is None:
        exit_code = _infer_exit_code(code)

    resp = JsonResponse(
        ok=False, error=err, type=type_, exit_code=exit_code,
        risk=risk if risk != "low" else None,
        confirmation_required=confirmation_required if confirmation_required else None,
        hint=hint if hint else None,
    )
    _tag_exit_code(exit_code)
    return resp.to_json()


def dry_run_plan(plan: dict, confirmation_id: str, type_: str = "") -> str:
    """创建 dry-run 响应。不修改退出码。"""
    resp = JsonResponse(ok=True, type=type_, dryRun=True, plan=plan)
    resp.metadata["confirmationId"] = confirmation_id
    _tag_exit_code(EXIT_SUCCESS)
    return resp.to_json()


def _infer_exit_code(code: str) -> int:
    """根据错误码推断退出码。"""
    usage_codes = {"missing_argument", "invalid_argument", "invalid_format", "parse_error"}
    auth_codes = {"auth_required", "permission_denied", "token_expired", "not_authenticated"}
    retry_codes = {"rate_limited", "service_unavailable", "timeout", "queue_full"}

    if code in usage_codes:
        return EXIT_USAGE_ERROR
    elif code in auth_codes:
        return EXIT_AUTH_ERROR
    elif code in retry_codes:
        return EXIT_RETRYABLE
    return EXIT_GENERAL_ERROR


def _tag_exit_code(code: int) -> None:
    """在进程上标记退出码，由 Typer exit hook 读取。"""
    # 存入全局变量，exit handler 会读取
    global _EXIT_CODE
    _EXIT_CODE = code


# ── 退出码钩子 ───────────────────────────────────────────────-

_EXIT_CODE: int = EXIT_SUCCESS


def get_exit_code() -> int:
    return _EXIT_CODE


def reset_exit_code() -> None:
    global _EXIT_CODE
    _EXIT_CODE = EXIT_SUCCESS
