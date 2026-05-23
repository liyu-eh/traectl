#!/usr/bin/env python3
"""traectl — 符合 agentic-cli-design 规范的 AI Agent 友好命令行工具。

特性：
- 默认 JSON 输出（machine-readable）
- --human 切回人类可读格式
- 标准化响应外壳 {"ok", "data", "error", "metadata"}
- 分类退出码（0/2/3/4）
- --debug / --dry-run 全命令支持
- --fields 字段投影
- introspection: commands/exit-codes/help --json
- install-skills 自安装
"""

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Annotated, Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from ..config import (
    CDP_HOST,
    CDP_PORT,
    EXIT_AUTH,
    EXIT_GENERAL,
    EXIT_RETRYABLE,
    EXIT_SUCCESS,
    EXIT_USAGE,
    SCHEMA_VERSION,
    SOLO_TIMEOUT,
    AGENT_ROLES,
    load_config,
    save_config,
)
from ..connection_pool import get_pool, close_pool
from ..controller import TraeSoloController
from ..response import ok as mk_ok, error as mk_error

# ── Rich 控制台（stderr——日志/进度，不污染 stdout） ──────


def _resolve_color_mode() -> str | None:
    """确定 Rich 颜色系统。遵守 NO_COLOR / FORCE_COLOR 规范（P0.20）。"""
    if os.environ.get("NO_COLOR", "").strip():
        return None  # 禁用颜色
    if os.environ.get("FORCE_COLOR", "").strip():
        return "truecolor"
    if os.environ.get("TERM", "") == "dumb":
        return None  # dumb 终端禁用颜色
    return None  # 默认 auto


console = Console(stderr=True, highlight=False, color_system=_resolve_color_mode())

# ── 全局状态 ──────────────────────────────────────────────────
_DEBUG_ENABLED = False
_RAW_OUTPUT = False  # 如果 --human，直接 print 而非 JSON
_YES_FLAG = False  # --yes 全局确认标志
_OUTPUT_FORMAT = "json"  # json 或 ndjson
_NDJSON_BUFFER: list[str] = []  # ndjson 缓冲

# ── 公共参数工厂函数 ────────────────────────────────────


def _host_opt(default=CDP_HOST):
    return typer.Option(default, "--host", help="CDP 主机")


def _port_opt(default=CDP_PORT):
    return typer.Option(default, "--port", help="CDP 端口")


def _workspace_opt(default=""):
    return typer.Option(default, "--workspace", "-w", help="工作区路径")

# ── Typer App ──────────────────────────────────────────────────

app = typer.Typer(
    name="traectl",
    help="traectl — 通过 CDP 控制 Trae CN SOLO 编码代理的命令行工具",
    no_args_is_help=True,
    add_completion=False,
    context_settings={"help_option_names": ["-h", "--help"]},
)

workspace_app = typer.Typer(
    name="workspace",
    help="工作区管理: 初始化项目、Skills 管理、MCP 配置",
    no_args_is_help=True,
)
app.add_typer(workspace_app, name="workspace")

config_app = typer.Typer(
    name="config",
    help="配置管理: 读取、设置、列出、导出配置项",
    no_args_is_help=True,
)
app.add_typer(config_app, name="config")

# ── 公共标志回调 ──────────────────────────────────────────────


def _debug_cb(val: bool):
    global _DEBUG_ENABLED
    _DEBUG_ENABLED = val
    return val


def _yes_cb(val: bool):
    global _YES_FLAG
    _YES_FLAG = val
    return val


def _human_cb(val: bool):
    global _RAW_OUTPUT
    _RAW_OUTPUT = val
    return val


def _output_cb(val: str):
    global _OUTPUT_FORMAT
    _OUTPUT_FORMAT = val
    return val


def _version_cb(val: bool):
    """--version / -V 回调：输出版本信息后立即退出。"""
    if val:
        info = _version_output()
        _display(mk_ok(info, type_="version.info"))
        _exit(EXIT_SUCCESS)
    return val


# ── 辅助 ───────────────────────────────────────────────────────


def _dbg(msg: str) -> None:
    """debug 日志到 stderr。"""
    if _DEBUG_ENABLED:
        console.print(f"[dim][debug][/dim] {msg}")


def _print_json(obj: Any) -> None:
    """打印 JSON 到 stdout。"""
    output = json.dumps(obj, ensure_ascii=False, indent=2) if isinstance(obj, dict) else str(obj)
    print(output)


def _ndjson_line(obj: dict) -> None:
    """输出单行 NDJSON 到 stdout 并 flush。"""
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _display(text: str) -> None:
    """展示输出。--human 时 Rich 高亮，否则当 JSON 处理。

    --output ndjson 时每行一个 JSON 对象。
    """
    if _OUTPUT_FORMAT == "ndjson":
        try:
            data = json.loads(text)
            print(json.dumps(data, ensure_ascii=False))
        except (json.JSONDecodeError, TypeError):
            print(text)
        return

    if _RAW_OUTPUT:
        try:
            data = json.loads(text)
            formatted = json.dumps(data, ensure_ascii=False, indent=2)
            syntax = Syntax(formatted, "json", theme="monokai", word_wrap=True)
            console.print(syntax)
        except (json.JSONDecodeError, TypeError):
            console.print(text)
    else:
        _print_json(text)


def _exit(code: int) -> None:
    """带退出码退出。"""
    raise typer.Exit(code=code)


@asynccontextmanager
async def solo_session(host: str = CDP_HOST, port: int = CDP_PORT, workspace: str = ""):
    """从连接池获取或创建持久 CDP 连接，命令执行完后归还而非断开。"""
    pool = get_pool()
    cdp = await pool.acquire(host, port)
    try:
        solo = TraeSoloController(cdp, workspace_root=workspace)
        yield solo
    finally:
        await pool.release(cdp)


def _run(coro, host: str, port: int, workspace: str):
    async def _wrapped():
        async with solo_session(host, port, workspace) as solo:
            return await coro(solo)
    try:
        result = asyncio.run(_wrapped())
        if result is not None:
            _display(result)
            # 从 JSON 响应中提取 exit_code
            try:
                parsed = json.loads(result)
                ec = parsed.get("exit_code", 0)
                if ec != 0:
                    _exit(ec)
            except (json.JSONDecodeError, TypeError):
                pass
    except RuntimeError as e:
        err_msg = mk_error("runtime_error", str(e), exit_code=EXIT_GENERAL, hint="检查 CDP 连接: traectl health")
        _print_json(err_msg)
        _exit(EXIT_GENERAL)
    except typer.Exit:
        raise
    except Exception as e:
        err_msg = mk_error("unexpected_error", f"{type(e).__name__}: {e}", exit_code=EXIT_GENERAL, hint="请重试或检查连接配置")
        _print_json(err_msg)
        _exit(EXIT_GENERAL)



# ===================================================================
# 全局公共参数注入（通过 callback）
# ===================================================================


def _version_output():
    from .. import __version__
    return {
        "version": __version__,
        "name": "traectl",
        "description": "traectl — 通过 CDP 控制 Trae CN SOLO 编码代理",
        "python": sys.version,
        "schema_version": SCHEMA_VERSION,
    }


@app.callback()
def main_callback(
    ctx: typer.Context,
    debug: bool = typer.Option(False, "--debug", help="启用调试日志（stderr）", callback=_debug_cb, is_eager=True),
    human: bool = typer.Option(False, "--human", help="人类可读输出格式（默认 JSON）", callback=_human_cb, is_eager=True),
    trace_id: Optional[str] = typer.Option(None, "--trace-id", help="追踪 ID（请求关联）"),
    show_version: bool = typer.Option(False, "--version", "-V", help="显示版本信息（等价于 traectl version）", callback=_version_cb, is_eager=True),
    yes: bool = typer.Option(False, "--yes", help="跳过高风险操作确认", callback=_yes_cb, is_eager=True),
    output: str = typer.Option("json", "--output", help="输出格式: json（默认）, ndjson（流式输出）", callback=_output_cb, is_eager=True),
):
    """traectl 命令行工具。默认输出 JSON，加 --human 输出人类可读格式。用 traectl version 查看版本。"""
    if debug:
        _dbg(f"trace_id={trace_id or 'none'}")


__all__ = [
    "app",
    "workspace_app",
    "config_app",
    # 全局状态
    "_DEBUG_ENABLED",
    "_RAW_OUTPUT",
    "_YES_FLAG",
    "_OUTPUT_FORMAT",
    "_NDJSON_BUFFER",
    # 工厂函数
    "_host_opt",
    "_port_opt",
    "_workspace_opt",
    # 辅助函数
    "_dbg",
    "_print_json",
    "_ndjson_line",
    "_display",
    "_exit",
    "_run",
    # 错误码
    "EXIT_SUCCESS",
    "EXIT_GENERAL",
    "EXIT_USAGE",
]
