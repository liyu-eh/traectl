#!/usr/bin/env python3
"""EditorMixin — 编辑器/文件：读取编辑器内容、文件变更管理。"""

import json

from ..response import StandardResponse
from ..js_templates import (
    query_editor_state,
    query_file_changes,
    click_accept_btn,
    click_reject_btn,
    salvage_editor_text,
)



class EditorMixin:
    """编辑器/文件 Mixin：读取编辑器、管理文件变更。"""

    async def get_active_editor(self) -> StandardResponse:
        """获取当前编辑器中打开的文件列表和激活文件内容。"""
        try:
            js = query_editor_state()
            result = await self._cdp.eval_js(js)
            data = json.loads(result)
            return StandardResponse(result=data, message="编辑器内容", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"获取编辑器内容失败: {e}", code=-1)

    async def list_file_changes(self) -> StandardResponse:
        """获取 SOLO Agent 当前提议的文件变更列表。"""
        try:
            js = query_file_changes()
            result = await self._cdp.eval_js(js)
            data = json.loads(result)
            return StandardResponse(result=data, message="文件变更列表", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"获取文件变更失败: {e}", code=-1)

    async def accept_change(self, file_path: str = "") -> StandardResponse:
        """接受 SOLO 提议的文件变更。"""
        try:
            js = click_accept_btn()
            result = await self._cdp.eval_js(js)
            return StandardResponse(result=result, message=f"接受变更: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"接受变更失败: {e}", code=-1)

    async def reject_change(self, file_path: str = "") -> StandardResponse:
        """拒绝 SOLO 提议的文件变更。"""
        try:
            js = click_reject_btn()
            result = await self._cdp.eval_js(js)
            return StandardResponse(result=result, message=f"拒绝变更: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"拒绝变更失败: {e}", code=-1)

    async def _salvage_editor_content(self) -> str:
        """超时时通过 CDP 检查编辑器是否有未保存的半成品代码。"""
        js = salvage_editor_text()
        try:
            content = await self._cdp.eval_js(js)
            if content and len(content) > 100:
                return f"\n\n[CDP 编辑器半成品]\n```\n{content}\n```"
            return ""
        except Exception:
            return ""
