from ._core import (
    app,
    _run,
    _host_opt,
    _port_opt,
    _workspace_opt,
    _print_json,
    _display,
    _exit,
    _YES_FLAG,
    mk_ok,
    mk_error,
    TraeSoloController,
    SOLO_TIMEOUT,
    AGENT_ROLES,
    EXIT_USAGE,
    EXIT_GENERAL,
)

import json
import os
from typing import Optional

import typer


@app.command()
def action(
    action_type: str = typer.Argument(..., help="操作类型: get_tasks, switch_task, delete_task, stop, open_settings, toggle_auto, open_file, confirm"),
    task_index: Optional[int] = typer.Option(None, "--task-index", "-i", help="switch_task 时目标索引"),
    file_path: Optional[str] = typer.Option(None, "--file-path", "-f", help="open_file 时文件路径"),
    enable_auto: bool = typer.Option(True, "--enable-auto/--disable-auto", help="toggle_auto 时是否启用"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """执行维护操作。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": action_type, "task_index": task_index, "file_path": file_path},
            f"action-{action_type}",
            type_="action.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        if action_type in ("delete_task", "stop"):
            if not _YES_FLAG:
                return mk_error("confirmation_required", f"高风险操作 '{action_type}' 需要 --yes 确认", risk="high", confirmation_required=True, hint=f"traectl action {action_type} --yes")
        action_map = {
            "get_tasks": solo.get_tasks,
            "delete_task": solo.delete_current_task,
            "stop": solo.stop_generating,
            "open_settings": solo.open_settings,
            "confirm": solo.auto_confirm,
        }
        if action_type in action_map:
            result = (await action_map[action_type]()).result
        elif action_type == "switch_task":
            if task_index is None:
                return mk_error("missing_argument", "switch_task 需要 --task-index 参数", exit_code=EXIT_USAGE, hint="traectl action switch_task --task-index <n>")
            result = (await solo.switch_task(task_index)).result
        elif action_type == "open_file":
            if not file_path:
                return mk_error("missing_argument", "open_file 需要 --file-path 参数", exit_code=EXIT_USAGE, hint="traectl action open_file --file-path <path>")
            result = (await solo.open_file(file_path)).result
        elif action_type == "toggle_auto":
            result = (await solo.toggle_auto_mode(enable_auto)).result
        else:
            return mk_error("invalid_argument", f"未知 action: {action_type}", exit_code=EXIT_USAGE, hint="有效的 action: get_tasks, switch_task, delete_task, stop, open_settings, toggle_auto, open_file, confirm")
        return mk_ok({"action": action_type, "result": result}, type_="action.exec")
    _run(_cmd, host, port, workspace)


@app.command()
def regenerate(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """重新生成 SOLO 的最后一条回复。"""
    if not _YES_FLAG:
        _print_json(mk_error("confirmation_required", "重新生成会丢弃当前进度，需要 --yes 确认", risk="high", confirmation_required=True, hint="traectl regenerate --yes"))
        return
    async def _cmd(solo: TraeSoloController):
        result = (await solo.regenerate_last()).result
        return mk_ok({"result": result}, type_="chat.regenerate")
    _run(_cmd, host, port, workspace)


@app.command(name="close-dialog")
def close_dialog(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """关闭界面上弹出的对话框/弹窗。"""
    async def _cmd(solo: TraeSoloController):
        result = (await solo.close_dialog()).result
        return mk_ok({"result": result}, type_="dialog.close")
    _run(_cmd, host, port, workspace)


@app.command(name="auto-recover")
def auto_recover(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """智能识别并自动处理页面弹窗（服务端异常、更新提示、排队、确认等）。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.auto_handle_dialog()
        return mk_ok(resp.result, type_="dialog.auto_recover")
    _run(_cmd, host, port, workspace)


@app.command(name="file-status")
def file_status(
    target_dir: str = typer.Option(".", "--dir", "-d", help="目标目录"),
    glob_pattern: str = typer.Option("*.html,*.py,*.js,*.css,*.json,*.md", "--glob", "-g", help="逗号分隔的 glob 模式"),
    fields: Optional[str] = typer.Option(None, "--fields", help="返回字段（逗号分隔）"),
):
    """监视指定目录的文件变化状态。支持 --fields 字段投影。"""
    import glob as glob_mod
    from datetime import datetime

    patterns = [p.strip() for p in glob_pattern.split(",")]
    files = []
    for p in patterns:
        for f in sorted(glob_mod.glob(os.path.join(target_dir, p))):
            if os.path.isfile(f):
                stat = os.stat(f)
                entry = {
                    "path": f,
                    "lines": sum(1 for _ in open(f, "rb") if _),
                    "size": stat.st_size,
                    "mtime": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
                # 字段投影
                if fields:
                    selected = fields.split(",")
                    entry = {k: v for k, v in entry.items() if k in selected}
                files.append(entry)
    _display(mk_ok(files, type_="file-status.list"))


@app.command()
def analyze(
    task: str = typer.Argument(..., help="任务描述"),
):
    """分析任务，推荐最佳 Agent 角色和模型。"""
    from ..project_manager import ProjectManager
    pm = ProjectManager(solo=None)
    result = pm.analyze_task(task)
    _display(mk_ok(result, type_="task.analyze"))


@app.command()
def plan(
    subtasks_json: str = typer.Argument(..., help="子任务列表 JSON"),
    timeout: int = typer.Option(SOLO_TIMEOUT, "--timeout", "-t", help="每个子任务超时秒数"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """多 Agent 计划执行。"""
    async def _cmd(solo: TraeSoloController):
        from ..project_manager import ProjectManager
        pm = ProjectManager(solo)
        try:
            subtasks = json.loads(subtasks_json)
        except json.JSONDecodeError as e:
            return mk_error("invalid_argument", f"JSON 解析失败: {e}", exit_code=EXIT_USAGE, hint="请提供有效的 JSON 格式的 subtasks_json 参数")
        for st in subtasks:
            role_config = AGENT_ROLES.get(st.get("role", ""), {})
            st["role_name"] = role_config.get("name", st.get("role", "unknown"))
        result = await pm.execute_plan(subtasks=subtasks, timeout_per_task=timeout)
        return mk_ok(result, type_="plan.execute")
    _run(_cmd, host, port, workspace)
