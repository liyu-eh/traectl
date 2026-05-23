from ._core import (
    app,
    workspace_app,
    config_app,
    _print_json,
    _display,
    _exit,
    _YES_FLAG,
    mk_ok,
    mk_error,
    EXIT_USAGE,
    EXIT_GENERAL,
    load_config,
    save_config,
)

import os
from typing import Optional

import typer


@app.command(name="install-skills")
def install_skills_cmd(
    target: str = typer.Option("./.agents/skills", "--target", "-t", help="安装目标路径"),
    global_install: bool = typer.Option(False, "--global", help="安装到全局 ~/.agents/skills"),
    claude_mode: bool = typer.Option(False, "--claude", help="安装为 Claude 兼容格式"),
    trae_mode: bool = typer.Option(False, "--trae", help="安装到 Trae CN 工作区 skills 目录"),
):
    """安装 traectl 自身的 Agent skill 到指定目录。"""
    import shutil
    from pathlib import Path

    if trae_mode and claude_mode:
        _print_json(mk_error("invalid_argument", "--trae 和 --claude 不能同时指定", exit_code=EXIT_USAGE, hint="请只使用 --trae 或 --claude 其中之一"))
        return

    # try new path first, fallback to old path
    skill_src = Path(__file__).parent.parent.parent / "agent" / "skills" / "traectl"
    if not skill_src.exists():
        skill_src = Path(__file__).parent.parent.parent / "agent" / "skills" / "trae-solo"
    if not skill_src.exists():
        skill_src = Path(__file__).parent.parent.parent / "skills" / "traectl"
    if not skill_src.exists():
        _print_json(mk_error("not_found", f"Skill 源目录不存在: {skill_src}", exit_code=EXIT_GENERAL, hint="请检查项目是否在 traectl-CLI 目录下运行"))
        return

    if trae_mode:
        # Trae CN workspace skills 目录
        workspace_dir = os.environ.get("TRAE_WORKSPACE", os.path.abspath("."))
        dest_base = Path(workspace_dir) / ".trae" / "skills"
    elif claude_mode:
        dest_base = Path.home() / ".claude" / "skills" if global_install else Path("./.claude/skills")
    else:
        dest_base = Path.home() / ".agents" / "skills" if global_install else Path(target)

    dest = dest_base / "traectl"
    dest.mkdir(parents=True, exist_ok=True)

    for f in skill_src.iterdir():
        if f.is_file():
            shutil.copy2(f, dest / f.name)

    _print_json(mk_ok({
        "source": str(skill_src),
        "destination": str(dest),
        "global": global_install,
        "claude": claude_mode,
        "trae": trae_mode,
        "files_installed": [f.name for f in skill_src.iterdir() if f.is_file()],
    }, type_="install-skills.result"))


# ===================================================================
# 子命令：workspace（子命令组）
# ===================================================================


@workspace_app.command(name="init")
def workspace_init(
    project_path: str = typer.Option(".", "--path", "-p", help="项目路径"),
    project_type: Optional[str] = typer.Option(None, "--type", help="项目类型 (python/nodejs/react/rust/go/mlops/devops)，留空自动检测"),
    skills: Optional[str] = typer.Option(None, "--skills", help="额外 skills，逗号分隔"),
):
    """初始化工作区：检测项目类型，创建目录结构，推荐并安装 skills。"""
    target = os.path.abspath(project_path)
    traefik_config = os.path.join(target, ".trae", "config.yaml")
    if os.path.exists(traefik_config) and not _YES_FLAG:
        _print_json(mk_error("confirmation_required", f"目标路径 '{target}' 已存在工作区配置，覆盖需要 --yes 确认", risk="medium", confirmation_required=True, hint=f"traectl workspace init --path {project_path} --yes"))
        return
    from ..workspace_manager import WorkspaceManager
    wm = WorkspaceManager()
    extra_skills = [s.strip() for s in skills.split(",")] if skills else None
    result = wm.setup_workspace(
        workspace_path=target,
        project_type=project_type,
        skills=extra_skills,
    )
    data = result.result or {}
    if result.message:
        data["message"] = result.message
    _display(mk_ok(data, type_="workspace.init"))


@workspace_app.command(name="setup-mcp")
def workspace_mcp(
    action: str = typer.Argument("list", help="操作: list, add, update, remove"),
    server_name: Optional[str] = typer.Option(None, "--name", help="MCP 服务器名称"),
    command: Optional[str] = typer.Option(None, "--command", help="启动命令"),
    args: Optional[str] = typer.Option(None, "--args", help="命令参数，逗号分隔"),
    env: Optional[str] = typer.Option(None, "--env", help="环境变量 KEY=VALUE，逗号分隔"),
    workspace_path: str = typer.Option(".", "--path", "-p", help="项目路径"),
):
    """管理 Trae CN MCP Server 配置。支持 add/list/update/remove 操作。"""
    from ..workspace_manager import WorkspaceManager
    wm = WorkspaceManager()

    if action == "list":
        result = wm.manage_mcp(workspace_path=os.path.abspath(workspace_path), action="list")
        data = result.result or {}
        if result.message:
            data["message"] = result.message
        _display(mk_ok(data, type_="workspace.mcp"))
    elif action in ("add", "update"):
        if not server_name or not command:
            _print_json(mk_error("invalid_argument", f"{action} 操作需要 --name 和 --command", exit_code=EXIT_USAGE, hint=f"traectl workspace setup-mcp {action} --name <server> --command <cmd>"))
            return
        server_config = {"command": command}
        if args:
            server_config["args"] = [a.strip() for a in args.split(",")]
        if env:
            server_config["env"] = dict(e.split("=", 1) for e in env.split(",") if "=" in e)
        result = wm.manage_mcp(
            workspace_path=os.path.abspath(workspace_path),
            action=action,
            server_name=server_name,
            server_config=server_config,
        )
        data = result.result or {}
        if result.message:
            data["message"] = result.message
        _display(mk_ok(data, type_="workspace.mcp"))
    elif action == "remove":
        if not server_name:
            _print_json(mk_error("invalid_argument", "remove 操作需要 --name", exit_code=EXIT_USAGE, hint="traectl workspace setup-mcp remove --name <server>"))
            return
        result = wm.manage_mcp(
            workspace_path=os.path.abspath(workspace_path),
            action="remove",
            server_name=server_name,
        )
        data = result.result or {}
        if result.message:
            data["message"] = result.message
        _display(mk_ok(data, type_="workspace.mcp"))
    else:
        _print_json(mk_error("invalid_argument", f"未知操作: {action}，支持: list, add, update, remove", exit_code=EXIT_USAGE, hint="traectl workspace setup-mcp list"))


# ===================================================================
# 子命令组：config
# ===================================================================


@config_app.command(name="get")
def config_get(
    key: Optional[str] = typer.Argument(None, help="配置键名（留空则返回所有）"),
):
    """读取配置项。"""
    cfg = load_config()
    if key:
        if key in cfg:
            _display(mk_ok({key: cfg[key]}, type_="config.get"))
        else:
            _print_json(mk_error("not_found", f"未知配置项: {key}", exit_code=EXIT_USAGE, hint="traectl config list 查看所有可用配置项"))
    else:
        _display(mk_ok(cfg, type_="config.list"))


@config_app.command(name="set")
def config_set(
    key: str = typer.Argument(..., help="配置键名"),
    value: str = typer.Argument(..., help="配置值"),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """设置配置项。"""
    valid_keys = {"cdp_host", "cdp_port", "solo_timeout", "stable_threshold", "poll_interval"}
    if key not in valid_keys:
        _print_json(mk_error("invalid_argument", f"无效配置项: {key}，有效值: {', '.join(sorted(valid_keys))}", exit_code=EXIT_USAGE, hint="traectl config set <key> <value>"))
        return
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan({"action": "config_set", "key": key, "value": value}, f"config-set-{key}", type_="config.set.dry-run"))
        return
    cfg = load_config()
    cfg[key] = value
    save_config(cfg)
    _display(mk_ok({key: value}, type_="config.set"))


@config_app.command(name="list")
def config_list():
    """列出所有配置项。"""
    cfg = load_config()
    _display(mk_ok(cfg, type_="config.list"))


@config_app.command(name="export")
def config_export():
    """导出所有配置为 JSON。"""
    cfg = load_config()
    _print_json(cfg)
