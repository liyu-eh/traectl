from ._core import (
    app,
    _run,
    _host_opt,
    _port_opt,
    _workspace_opt,
    _dbg,
    _print_json,
    _ndjson_line,
    _display,
    _exit,
    _OUTPUT_FORMAT,
    mk_ok,
    mk_error,
    TraeSoloController,
    SOLO_TIMEOUT,
    EXIT_USAGE,
)

import asyncio
import time
from typing import Optional

import typer


@app.command()
def new(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """创建新的空任务会话。"""
    async def _cmd(solo: TraeSoloController):
        result = (await solo.start_new_task()).result
        return mk_ok({"result": result}, type_="task.new")
    _run(_cmd, host, port, workspace)


@app.command()
def send(
    message: str = typer.Argument(..., help="要发送的消息"),
    wait: bool = typer.Option(False, "--wait", help="等待 SOLO 响应完成"),
    no_wait: bool = typer.Option(False, "--no-wait", help="不等待回复，立即返回（默认行为）"),
    timeout: int = typer.Option(SOLO_TIMEOUT, "--timeout", "-t", help="等待超时秒数"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """在当前聊天中输入文本并发送。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": "send_message", "message_length": len(message), "wait": wait},
            f"send-{hash(message) % 10**6:06x}",
            type_="message.send.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        if wait:
            r1 = (await solo.type_message(message)).result
            r2 = (await solo.send_message()).result
            if r2 != "sent":
                return mk_ok({"input": r1, "send": r2, "status": "failed"}, type_="message.send")
            if _OUTPUT_FORMAT == "ndjson":
                # ndjson 流式：后台等待响应，每5秒输出进度
                task = asyncio.create_task(solo._wait_for_response(timeout))
                start = time.monotonic()
                while True:
                    done, _ = await asyncio.wait({task}, timeout=5.0)
                    elapsed = int(time.monotonic() - start)
                    if done:
                        break
                    _ndjson_line({"type": "task.progress", "elapsed": elapsed, "status": "waiting"})
                resp = task.result()
                _ndjson_line({"type": "task.complete", "data": {"content": resp.result or resp.message}})
                return None  # 已直接输出，不经过 _display
            resp = await solo._wait_for_response(timeout)
            return mk_ok({"content": resp.result or resp.message}, type_="message.send")
        r1 = (await solo.type_message(message)).result
        r2 = (await solo.send_message()).result
        if r2 == "sent":
            info = {"input": r1, "send": r2, "status": "sent"}
            if no_wait or not wait:  # split-flow
                info["mode"] = "split-flow"
                info["poll_hint"] = f"Use: traectl status --port {port} to check task progress, or traectl chat --port {port} to read the response"
            return mk_ok(info, type_="message.send" if (no_wait or not wait) else "message.send.wait")
        return mk_ok({"input": r1, "send": r2, "status": "failed"}, type_="message.send")
    _run(_cmd, host, port, workspace)


@app.command(name="file-changes")
def file_changes(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """获取 SOLO Agent 当前提议的文件变更列表。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.list_file_changes()
        data = resp.result
        return mk_ok(data, type_="file-changes.list")
    _run(_cmd, host, port, workspace)


@app.command()
def accept(
    file_path: str = typer.Option("", "--file-path", "-f", help="指定文件路径（留空则接受所有）"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """接受 SOLO 提议的文件变更。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": "accept_change", "file_path": file_path or "all"},
            f"accept-{file_path or 'all'}",
            type_="file-change.accept.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        result = (await solo.accept_change(file_path)).result
        return mk_ok({"file_path": file_path or "all", "result": result}, type_="file-change.accept")
    _run(_cmd, host, port, workspace)


@app.command()
def reject(
    file_path: str = typer.Option("", "--file-path", "-f", help="指定文件路径（留空则拒绝所有）"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """拒绝 SOLO 提议的文件变更。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": "reject_change", "file_path": file_path or "all"},
            f"reject-{file_path or 'all'}",
            type_="file-change.reject.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        result = (await solo.reject_change(file_path)).result
        return mk_ok({"file_path": file_path or "all", "result": result}, type_="file-change.reject")
    _run(_cmd, host, port, workspace)


@app.command()
def terminal(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """切换终端面板的显示/隐藏。"""
    async def _cmd(solo: TraeSoloController):
        result = (await solo.toggle_terminal()).result
        return mk_ok({"result": result}, type_="terminal.toggle")
    _run(_cmd, host, port, workspace)


@app.command(name="exec")
def exec_cmd(
    command: str = typer.Argument(..., help="要执行的命令"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """在 Trae CN 终端中执行命令。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": "exec", "command": command},
            f"exec-{hash(command) % 10**6:06x}",
            type_="terminal.exec.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        result = (await solo.execute_in_terminal(command)).result
        return mk_ok({"command": command, "result": result}, type_="terminal.exec")
    _run(_cmd, host, port, workspace)


@app.command()
def git(
    action_type: str = typer.Argument(..., help="操作: status, stage, commit, diff, log, branch"),
    file_path: str = typer.Option("", "--file-path", "-f", help="stage 时指定文件路径"),
    message: str = typer.Option("", "--message", "-m", help="commit 时提交信息"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """Git 综合操作。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": action_type, "file_path": file_path, "message_set": bool(message)},
            f"git-{action_type}",
            type_="git.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        result = (await solo.git(action_type, file_path, message)).result
        return mk_ok({"action": action_type, "result": result}, type_="git.exec")
    _run(_cmd, host, port, workspace)


@app.command()
def screenshot(
    save_path: Optional[str] = typer.Option(None, "--save-path", "-s", help="保存到文件路径"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """截取 Trae CN SOLO 界面截图。"""
    async def _cmd(solo: TraeSoloController):
        if save_path:
            path = (await solo.screenshot_to_file(save_path)).result
            return mk_ok({"path": path}, type_="screenshot.save")
        else:
            data = (await solo.screenshot()).result
            return mk_ok({"base64_length": len(data), "format": "png"}, type_="screenshot.capture")
    _run(_cmd, host, port, workspace)


@app.command(name="terminal-content")
def terminal_content(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """获取终端面板的文本内容。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.get_terminal_content()
        data = resp.result
        return mk_ok(data, type_="terminal.content")
    _run(_cmd, host, port, workspace)
