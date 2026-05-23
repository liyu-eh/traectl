from ._core import (
    app,
    _run,
    _host_opt,
    _port_opt,
    _workspace_opt,
    _display,
    _exit,
    _print_json,
    _version_output,
    _RAW_OUTPUT,
    mk_ok,
    mk_error,
    TraeSoloController,
    SOLO_TIMEOUT,
    AGENT_ROLES,
    EXIT_USAGE,
)

from typing import Optional

import typer


@app.command()
def models(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """列出所有可用模型及当前选中模型。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.list_models()
        data = resp.result
        return mk_ok(data, type_="models.list")
    _run(_cmd, host, port, workspace)


@app.command()
def switch(
    model_name: str = typer.Argument(..., help="模型名称，如 DeepSeek-V4-Pro"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
    dry_run: bool = typer.Option(False, "--dry-run", help="演示模式"),
):
    """切换 SOLO 模型。"""
    if dry_run:
        from ..response import dry_run_plan
        _print_json(dry_run_plan(
            {"action": "switch_model", "model": model_name},
            f"switch-{model_name}",
            type_="model.switch.dry-run",
        ))
        return
    async def _cmd(solo: TraeSoloController):
        resp = await solo.switch_model(model_name)
        result = resp.result
        return mk_ok({"result": result, "model": model_name}, type_="model.switch")
    _run(_cmd, host, port, workspace)


@app.command()
def chat(
    max_length: int = typer.Option(5000, "--max-length", "-l", help="返回内容最大长度"),
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """读取 SOLO 聊天记录。"""
    async def _cmd(solo: TraeSoloController):
        content = (await solo.get_chat_content(max_length=max_length)).result
        return mk_ok({"content": content, "length": len(content)}, type_="chat.read")
    _run(_cmd, host, port, workspace)


@app.command()
def roles():
    """列出所有可用的 Agent 角色及推荐模型。"""
    data = {
        k: {"name": v["name"], "description": v["description"], "recommended_models": v["recommended_models"]}
        for k, v in AGENT_ROLES.items()
    }
    _display(mk_ok(data, type_="roles.list"))


@app.command()
def status(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """获取 SOLO Agent 当前状态。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.get_solo_status()
        data = resp.result
        return mk_ok(data, type_="status.get")
    _run(_cmd, host, port, workspace)


@app.command()
def health(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """检查 traectl MCP Server 健康状态。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.get_health_info()
        return mk_ok(resp.result, type_="health.check")
    _run(_cmd, host, port, workspace)


# ===================================================================
# 子命令：version
# ===================================================================


@app.command(name="version")
def version_cmd(
    json_output: bool = typer.Option(True, "--json", help="以 JSON 格式输出版本信息"),
    human: bool = typer.Option(False, "--human", help="以人类可读格式输出版本信息"),
):
    """输出版本信息。等价于 traectl --version，但支持 --json 和 --human 切换。"""
    info = _version_output()
    if human:
        global _RAW_OUTPUT
        _RAW_OUTPUT = True
    _display(mk_ok(info, type_="version.info"))


@app.command()
def editor(
    host: str = _host_opt(),
    port: int = _port_opt(),
    workspace: str = _workspace_opt(),
):
    """获取当前编辑器中打开的文件列表和激活文件内容。"""
    async def _cmd(solo: TraeSoloController):
        resp = await solo.get_active_editor()
        data = resp.result
        return mk_ok(data, type_="editor.status")
    _run(_cmd, host, port, workspace)
