from ._core import (
    app,
    _display,
    _print_json,
    _exit,
    mk_ok,
    mk_error,
    EXIT_USAGE,
)

from typing import Optional

import typer

from ..platform import get_platform_info

# Command metadata: risk level, confirmation requirements, hints
COMMAND_METADATA = {
    "submit": {"risk": "low", "confirmation_required": False, "hint": "traectl submit <task_file>", "category": "task"},
    "health": {"risk": "low", "confirmation_required": False, "hint": "traectl health", "category": "status"},
    "models": {"risk": "low", "confirmation_required": False, "hint": "traectl models", "category": "status"},
    "switch": {"risk": "medium", "confirmation_required": False, "hint": "traectl switch <model>", "category": "model"},
    "status": {"risk": "low", "confirmation_required": False, "hint": "traectl status", "category": "status"},
    "chat": {"risk": "low", "confirmation_required": False, "hint": "traectl chat", "category": "status"},
    "editor": {"risk": "low", "confirmation_required": False, "hint": "traectl editor", "category": "status"},
    "file-changes": {"risk": "low", "confirmation_required": False, "hint": "traectl file-changes", "category": "file"},
    "accept": {"risk": "high", "confirmation_required": True, "hint": "traectl accept --yes", "category": "file"},
    "reject": {"risk": "high", "confirmation_required": True, "hint": "traectl reject --yes", "category": "file"},
    "file-status": {"risk": "low", "confirmation_required": False, "hint": "traectl file-status", "category": "file"},
    "screenshot": {"risk": "low", "confirmation_required": False, "hint": "traectl screenshot", "category": "utility"},
    "terminal": {"risk": "medium", "confirmation_required": False, "hint": "traectl terminal <cmd>", "category": "terminal"},
    "exec": {"risk": "medium", "confirmation_required": False, "hint": "traectl exec <cmd>", "category": "terminal"},
    "terminal-content": {"risk": "low", "confirmation_required": False, "hint": "traectl terminal-content", "category": "terminal"},
    "git": {"risk": "medium", "confirmation_required": False, "hint": "traectl git <op>", "category": "git"},
    "action": {"risk": "medium", "confirmation_required": False, "hint": "traectl action <type>", "category": "agent"},
    "roles": {"risk": "low", "confirmation_required": False, "hint": "traectl roles", "category": "agent"},
    "analyze": {"risk": "low", "confirmation_required": False, "hint": "traectl analyze <task>", "category": "agent"},
    "plan": {"risk": "low", "confirmation_required": False, "hint": "traectl plan <task>", "category": "agent"},
    "new": {"risk": "medium", "confirmation_required": True, "hint": "traectl new --yes", "category": "agent"},
    "send": {"risk": "low", "confirmation_required": False, "hint": "traectl send <message>", "category": "agent"},
    "regenerate": {"risk": "high", "confirmation_required": True, "hint": "traectl regenerate --yes", "category": "agent"},
    "close-dialog": {"risk": "low", "confirmation_required": False, "hint": "traectl close-dialog", "category": "utility"},
    "auto-recover": {"risk": "low", "confirmation_required": False, "hint": "traectl auto-recover", "category": "utility"},
    "install-skills": {"risk": "low", "confirmation_required": False, "hint": "traectl install-skills [--trae]", "category": "setup"},
    "workspace": {"risk": "medium", "confirmation_required": False, "hint": "traectl workspace <subcommand>", "category": "setup"},
    "config": {"risk": "medium", "confirmation_required": False, "hint": "traectl config <get|set|list>", "category": "setup"},
    "commands": {"risk": "low", "confirmation_required": False, "hint": "traectl commands", "category": "introspect"},
    "help": {"risk": "low", "confirmation_required": False, "hint": "traectl help [command]", "category": "introspect"},
    "schema": {"risk": "low", "confirmation_required": False, "hint": "traectl schema [--command <name>]", "category": "introspect"},
    "exit-codes": {"risk": "low", "confirmation_required": False, "hint": "traectl exit-codes", "category": "introspect"},
    "version": {"risk": "low", "confirmation_required": False, "hint": "traectl version", "category": "introspect"},
    "categories": {"risk": "low", "confirmation_required": False, "hint": "traectl categories", "category": "introspect"},
    "doctor": {"risk": "low", "confirmation_required": False, "hint": "traectl doctor", "category": "introspect"},
}

# Parameter validation rules
PARAM_VALIDATION = {
    "action": {
        "action_type": {"allowed": ["get_tasks", "switch_task", "delete_task", "stop", "open_settings", "toggle_auto", "open_file", "confirm"], "description": "操作类型"},
    },
    "switch": {
        "model_name": {"description": "模型名称", "example": "DeepSeek-V4-Pro"},
    },
    "git": {
        "action_type": {"allowed": ["status", "stage", "commit", "diff", "log", "branch"], "description": "Git 操作"},
    },
    "submit": {
        "prompt": {"description": "任务文件路径 (.txt 或 .md)", "pattern": ".*\\.(txt|md)$"},
    },
}


@app.command(name="commands")
def commands_cmd(
    output_json: bool = typer.Option(True, "--json", help="以 JSON 格式输出命令列表"),
):
    """列出所有可用命令。等价于 traectl commands --json。"""
    commands_list = []
    for cmd in app.registered_commands:
        cmd_name = cmd.name if cmd.name else (cmd.callback.__name__ if cmd.callback else "unknown")
        meta = COMMAND_METADATA.get(cmd_name, {})
        commands_list.append({
            "name": cmd_name,
            "help": cmd.help or "",
            "risk": meta.get("risk", "low"),
            "category": meta.get("category", "other"),
            "hint": meta.get("hint", ""),
            "params": [
                {
                    "name": p.name,
                    "type": str(p.type.__name__) if p.type else "str",
                    "required": p.required,
                    "default": str(p.default) if p.default is not None else None,
                    "help": p.help or "",
                }
                for p in (getattr(cmd, 'params', None) or [])
            ],
        })
    for group_info in app.registered_groups:
        _group = group_info.typer_instance
        if _group is None:
            continue
        group_name = group_info.name or ""
        meta = COMMAND_METADATA.get(group_name, {})
        commands_list.append({
            "name": group_name,
            "help": getattr(group_info, 'help', '') or "",
            "risk": meta.get("risk", "low"),
            "category": meta.get("category", "other"),
            "hint": meta.get("hint", ""),
            "subcommands": [
                {
                    "name": sub.name,
                    "help": sub.help or "",
                }
                for sub in (getattr(_group, 'registered_commands', None) or [])
            ],
        })
    _display(mk_ok({"commands": commands_list, "count": len(commands_list)}, type_="commands.list"))


@app.command(name="help")
def help_cmd(
    command_name: Optional[str] = typer.Argument(None, help="要查看帮助的命令名称"),
):
    """显示帮助信息。JSON 模式输出结构化 introspective 帮助。
    
    不指定命令名时列出所有命令概览。
    指定命令名时输出该命令的详细参数 schema。
    """
    if command_name:
        found = None
        for cmd in app.registered_commands:
            name = cmd.name if cmd.name else (cmd.callback.__name__ if cmd.callback else None)
            if name == command_name:
                found = cmd
                break
        if not found:
            for group_info in app.registered_groups:
                group_app = group_info.typer_instance
                if group_app is None:
                    continue
                group_name = group_info.name
                for sub in (group_app.registered_commands or []):
                    sub_name = sub.name if sub.name else (sub.callback.__name__ if sub.callback else '')
                    full_name = f"{group_name} {sub_name}"
                    if full_name == command_name or sub_name == command_name:
                        found = sub
                        break
                if found:
                    break
        if not found:
            # 检查是否是子命令组名（如 config、workspace）
            for group_info in app.registered_groups:
                if group_info.name == command_name:
                    sub_list = []
                    group_app = group_info.typer_instance
                    if group_app:
                        for sub in (getattr(group_app, 'registered_commands', None) or []):
                            sub_name = sub.name if sub.name else (sub.callback.__name__ if sub.callback else '')
                            sub_list.append({"name": sub_name, "description": sub.help or ""})
                    _display(mk_ok({
                        "group": command_name,
                        "description": group_info.help or "",
                        "subcommands": sub_list,
                    }, type_="help.group"))
                    return
            _print_json(mk_error("not_found", f"命令不存在: {command_name}。用 traectl commands 查看所有命令。", exit_code=EXIT_USAGE, hint="traectl commands 查看所有命令"))
            return

        schema = _build_command_schema(found)
        _display(mk_ok({
            "command": command_name,
            "description": found.help or "",
            "parameters": schema["params"],
        }, type_="help.command"))
    else:
        all_cmds = []
        for cmd in app.registered_commands:
            name = cmd.name if cmd.name else (cmd.callback.__name__ if cmd.callback else "")
            all_cmds.append({"name": name, "description": cmd.help or ""})
        for group_info in app.registered_groups:
            group_app = group_info.typer_instance
            if group_app is None:
                continue
            group_name = group_info.name
            sub_list = []
            for sub in (getattr(group_app, 'registered_commands', None) or []):
                sub_list.append({"name": sub.name, "description": sub.help or ""})
            all_cmds.append({"name": group_name, "subcommands": sub_list})
        _display(mk_ok({"commands": all_cmds, "usage": f"traectl <command> --json 或 traectl help <command>"}, type_="help.list"))


@app.command(name="schema")
def schema_cmd(
    command: Optional[str] = typer.Option(None, "--command", "-c", help="指定命令名"),
):
    """输出命令的 JSON Schema（introspection）。"""
    if command:
        for cmd in app.registered_commands:
            if cmd.name == command or (cmd.name is None and cmd.callback and cmd.callback.__name__ == command):
                schema = _build_command_schema(cmd)
                _display(mk_ok(schema, type_="schema.command"))
                return
        _print_json(mk_error("not_found", f"未知命令: {command}", exit_code=EXIT_USAGE, hint="traectl commands 查看所有命令"))
    else:
        schemas = []
        for cmd in app.registered_commands:
            schemas.append(_build_command_schema(cmd))
        _display(mk_ok({"commands": schemas, "count": len(schemas)}, type_="schema.list"))


def _resolve_default(value):
    import inspect
    import typer.models
    while isinstance(value, (typer.models.OptionInfo, typer.models.ArgumentInfo)):
        value = getattr(value, 'default', None)
    if value is None or value is inspect.Parameter.empty:
        return None
    return repr(value)


def _build_command_schema(cmd) -> dict:
    import inspect
    sig = inspect.signature(cmd.callback) if cmd.callback else inspect.Signature()
    params = []
    cmd_name = cmd.name if cmd.name else (cmd.callback.__name__ if cmd.callback else "unknown")
    for name, param in sig.parameters.items():
        if name in ('ctx', 'self'):
            continue
        ptype = 'str'
        ann = param.annotation
        if ann is not inspect.Parameter.empty:
            if hasattr(ann, '__name__'):
                ptype = ann.__name__
            else:
                ptype = str(ann)
        param_info = {
            "name": name,
            "type": ptype,
            "required": param.default is inspect.Parameter.empty,
            "default": _resolve_default(param.default),
        }
        # Add validation rules if available
        if cmd_name in PARAM_VALIDATION and name in PARAM_VALIDATION[cmd_name]:
            param_info["validation"] = PARAM_VALIDATION[cmd_name][name]
        params.append(param_info)
    meta = COMMAND_METADATA.get(cmd_name, {})
    schema = {
        "name": cmd_name,
        "description": cmd.help or "",
        "params": params,
        "risk": meta.get("risk", "low"),
        "confirmation_required": meta.get("confirmation_required", False),
        "hint": meta.get("hint", ""),
        "category": meta.get("category", "other"),
    }
    if cmd_name in PARAM_VALIDATION:
        schema["validation"] = PARAM_VALIDATION[cmd_name]
    return schema


@app.command(name="exit-codes")
def exit_codes_cmd(
    output_json: bool = typer.Option(True, "--json", help="以 JSON 格式输出退出码说明"),
):
    """列出所有退出码说明。"""
    codes = [
        {"code": 0, "name": "EXIT_SUCCESS", "description": "操作成功"},
        {"code": 1, "name": "EXIT_GENERAL", "description": "一般错误"},
        {"code": 2, "name": "EXIT_USAGE", "description": "无效参数或用法错误"},
        {"code": 3, "name": "EXIT_AUTH", "description": "认证或权限错误"},
        {"code": 4, "name": "EXIT_RETRYABLE", "description": "可重试错误（限流、网络超时等）"},
        {"code": 10, "name": "EXIT_CONFIRMATION_REQUIRED", "description": "需要确认（高风险操作）"},
    ]
    _display(mk_ok({"exit_codes": codes}, type_="exit-codes.list"))


CATEGORY_DESCRIPTIONS = {
    "task": "任务提交与执行",
    "status": "状态查询",
    "model": "模型管理",
    "file": "文件管理",
    "terminal": "终端操作",
    "git": "Git 操作",
    "agent": "Agent 管理",
    "utility": "辅助工具",
    "setup": "配置与工作区",
    "introspect": "自省与帮助",
    "other": "其他",
}


@app.command(name="categories")
def categories_cmd():
    """按类别分组列出所有命令。"""
    categories_map = {cat: [] for cat in CATEGORY_DESCRIPTIONS}
    for cmd in app.registered_commands:
        if not cmd.name:
            continue
        meta = COMMAND_METADATA.get(cmd.name, {})
        cat = meta.get("category", "other")
        categories_map.setdefault(cat, []).append({
            "name": cmd.name,
            "risk": meta.get("risk", "low"),
            "hint": meta.get("hint", ""),
        })
    for group_info in app.registered_groups:
        group_name = group_info.name
        if group_name is None:
            continue
        meta = COMMAND_METADATA.get(group_name, {})
        cat = meta.get("category", "other")
        categories_map.setdefault(cat, []).append({
            "name": group_name,
            "risk": meta.get("risk", "low"),
            "hint": meta.get("hint", ""),
        })
        group_app = group_info.typer_instance
        if group_app:
            for sub in (getattr(group_app, 'registered_commands', None) or []):
                sub_name = sub.name if sub.name else (sub.callback.__name__ if sub.callback else "")
                if not sub_name:
                    continue
                full_name = f"{group_name} {sub_name}"
                categories_map.setdefault(cat, []).append({
                    "name": full_name,
                    "risk": meta.get("risk", "low"),
                    "hint": meta.get("hint", ""),
                })
    categories = []
    for cat_name, desc in CATEGORY_DESCRIPTIONS.items():
        cmds = categories_map.get(cat_name, [])
        if cmds:
            categories.append({
                "name": cat_name,
                "description": desc,
                "commands": cmds,
            })
    _display(mk_ok({"categories": categories}, type_="categories.list"))


@app.command(name="doctor")
def doctor_cmd():
    """输出平台诊断信息（系统、Python、temp_dir、config_dir、CDP 配置等）。"""
    info = get_platform_info()
    _display(mk_ok(info, type_="doctor.info"))
