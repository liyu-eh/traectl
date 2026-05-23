#!/usr/bin/env python3
"""TerminalMixin — 终端控制：切换、读取、执行命令。"""

import asyncio
import json

from ..response import StandardResponse
from ..js_templates import (
    check_xterm_status,
    read_xterm_content,
    check_xterm_visible,
    type_terminal_command,
    focus_xterm,
    read_xterm_output,
)



class TerminalMixin:
    """终端控制 Mixin：切换终端、读取内容、执行命令。"""

    async def toggle_terminal(self) -> StandardResponse:
        """切换终端面板的显示/隐藏 (Ctrl+`)。"""
        try:
            await self._cdp.dispatch_key_combo(["Control", "`"])
            await asyncio.sleep(0.8)
            js = check_xterm_status()
            status = await self._cdp.eval_js(js)
            return StandardResponse(result=status, message="终端面板已切换", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"切换终端失败: {e}", code=-1)

    async def get_terminal_content(self) -> StandardResponse:
        """获取终端面板的文本内容。"""
        try:
            js = read_xterm_content()
            result = await self._cdp.eval_js(js)
            data = json.loads(result)
            return StandardResponse(result=data, message="终端内容", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"获取终端内容失败: {e}", code=-1)

    async def execute_in_terminal(self, command: str) -> StandardResponse:
        """在 Trae CN 终端中执行命令。先确保终端可见，输入命令并按 Enter。"""
        try:
            json_cmd = json.dumps(command)
            js_check = check_xterm_visible()
            term_status = await self._cdp.eval_js(js_check)
            if term_status != 'yes':
                await self._cdp.dispatch_key_combo(["Control", "`"])
                await asyncio.sleep(1)
                term_status = await self._cdp.eval_js(js_check)
                if term_status != 'yes':
                    await self._cdp.dispatch_key_combo(["Control", "Shift", "KeyP"])
                    await asyncio.sleep(1)
                    js_type = type_terminal_command()
                    await self._cdp.eval_js(js_type)
                    await asyncio.sleep(0.5)
                    await self._cdp.dispatch_key_combo(["Enter"])
                    await asyncio.sleep(2)

            try:
                js_focus = focus_xterm()
                await self._cdp.eval_js(js_focus)
            except Exception:
                pass

            for ch in command:
                await self._cdp.dispatch_key_event(ch, ch, "keyDown", 0)
                await asyncio.sleep(0.01)
                await self._cdp.dispatch_key_event(ch, ch, "keyUp", 0)
            await asyncio.sleep(0.1)
            await self._cdp.dispatch_key_event("Enter", "Enter", "keyDown", 0)
            await asyncio.sleep(0.05)
            await self._cdp.dispatch_key_event("Enter", "Enter", "keyUp", 0)

            await asyncio.sleep(1)

            js_read = read_xterm_output()
            output = await self._cdp.eval_js(js_read)
            return StandardResponse(result=output, message=f"命令已执行: {command}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"终端执行失败: {e}", code=-1)
