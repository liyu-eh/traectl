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
    EXIT_GENERAL,
)

import asyncio
import time
from typing import Optional

import typer


@app.command()
def submit(
    prompt: str = typer.Argument(..., help="任务描述"),
    role: Optional[str] = typer.Option(None, "--role", "-r", help="Agent 角色 (architect, frontend, backend, tester, reviewer, debugger)"),
    model: Optional[str] = typer.Option(None, "--model", "-m", help="指定模型名称"),
    no_wait: bool = typer.Option(False, "--no-wait", help="不等待响应完成"),
    wait_for_idle: bool = typer.Option(True, "--wait-for-idle/--no-wait-for-idle", help="提交前等待活动任务完成（默认开启）"),
    timeout: int = typer.Option(SOLO_TIMEOUT, "--timeout", "-t", help="等待超时秒数"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式：显示即将执行的操作"),
):
    """向 Trae CN SOLO 提交编码任务。
    
    默认输出 JSON 响应：{ok, data, metadata}。
    用 --human 切换为人类可读格式。
    """
    if dry_run:
        plan = {
            "action": "submit_task",
            "prompt_length": len(prompt),
            "role": role or "default",
            "model": model or "current",
            "wait_for_response": not no_wait,
            "wait_for_idle": wait_for_idle,
            "timeout": timeout,
        }
        from ..response import dry_run_plan
        import hashlib
        cid = hashlib.md5(prompt.encode()).hexdigest()[:12]
        _print_json(dry_run_plan(plan, cid, type_="task.submit.dry-run"))
        return

    async def _cmd(solo: TraeSoloController):
        _dbg(f"submitting task: role={role}, model={model}, timeout={timeout}")
        if _OUTPUT_FORMAT == "ndjson" and not no_wait:
            # ndjson 流式：后台等待响应，每5秒输出进度
            if role:
                coro = solo.submit_task_with_role(
                    prompt=prompt, role=role, model=model,
                    wait_for_response=True, timeout=timeout,
                    wait_for_idle=wait_for_idle,
                )
            else:
                coro = solo.submit_task(
                    prompt=prompt, wait_for_response=True, timeout=timeout,
                    wait_for_idle=wait_for_idle,
                )
            task = asyncio.create_task(coro)
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
        if role:
            resp = await solo.submit_task_with_role(
                prompt=prompt, role=role, model=model,
                wait_for_response=not no_wait, timeout=timeout,
                wait_for_idle=wait_for_idle,
            )
        else:
            resp = await solo.submit_task(
                prompt=prompt, wait_for_response=not no_wait, timeout=timeout,
                wait_for_idle=wait_for_idle,
            )
        if no_wait:
            return mk_ok({
                "content": resp.result or resp.message,
                "mode": "split-flow",
                "poll_hint": f"Use: traectl status --port {port} to check task progress, or traectl chat --port {port} to read the response",
            }, type_="task.submit.split-flow")
        return mk_ok({"content": resp.result or resp.message}, type_="task.submit")
    _run(_cmd, host, port, workspace)
