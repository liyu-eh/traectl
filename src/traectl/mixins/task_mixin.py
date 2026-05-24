#!/usr/bin/env python3
"""TaskMixin — 任务管理：提交任务、设置、模式切换、任务操作。"""

import asyncio
import json
import logging
from typing import Optional

from ..config import AGENT_ROLES, SELECTORS, SOLO_TIMEOUT
from ..response import StandardResponse
from ..js_templates import (
    type_command_palette,
    toggle_auto_mode,
    query_tasks_detailed,
    click_task_item,
    click_delete_task_btn,
    click_stop_btn,
    type_quick_open,
)


logger = logging.getLogger("traectl.controller")


class TaskMixin:
    """任务管理 Mixin：提交任务、打开设置、切换模式、任务列表操作。"""

    async def ensure_idle(self, timeout: int = 300) -> StandardResponse:
        """确保 SOLO 处于空闲状态。如果正在生成则等待完成。"""
        status = await self.get_solo_status()
        data = status.result if hasattr(status, 'result') else {}
        is_thinking = data.get('isThinking', False) if isinstance(data, dict) else False

        if not is_thinking:
            return StandardResponse(result=None, message='SOLO 已空闲', code=0)

        # 有活动任务，等待完成
        result = await self._wait_for_response(timeout)
        if result.code == 0:
            return StandardResponse(result=None, message='SOLO 已完成活动任务', code=0)
        return result

    async def submit_task(
        self,
        prompt: str,
        wait_for_response: bool = True,
        timeout: Optional[int] = None,
        wait_for_idle: bool = True,
    ) -> StandardResponse:
        await self._cdp.ensure_connected()
        timeout = timeout or SOLO_TIMEOUT

        if wait_for_idle:
            idle_resp = await self.ensure_idle(timeout=timeout)
            if idle_resp.code != 0:
                return idle_resp

        r1_resp = await self.start_new_task()
        r2_resp = await self.type_message(prompt)
        r3_resp = await self.send_message()

        r1 = r1_resp.result
        r2 = r2_resp.result
        r3 = r3_resp.result

        if r3 != "sent":
            return StandardResponse(result=None, message=f"发送失败: {r3}\n输入状态: {r2}", code=-1)

        if not wait_for_response:
            return StandardResponse(result="任务已提交，不等待响应", message="任务已提交，不等待响应", code=0)

        result = await self._wait_for_response(timeout)
        return result

    async def submit_task_with_role(
        self,
        prompt: str,
        role: str,
        model: Optional[str] = None,
        wait_for_response: bool = True,
        timeout: Optional[int] = None,
        wait_for_idle: bool = True,
    ) -> StandardResponse:
        role_config = AGENT_ROLES.get(role)
        if not role_config:
            return StandardResponse(result=None, message=f"未知角色: {role}。可用角色: {list(AGENT_ROLES.keys())}", code=-1)

        if not model:
            model = role_config["recommended_models"][0]

        switch_result = await self.switch_model(model)
        logger.info(f"模型切换: {switch_result.message}")

        full_prompt = f"[{role_config['name']}] {role_config['prompt_prefix']}\n\n任务: {prompt}"
        return await self.submit_task(full_prompt, wait_for_response, timeout, wait_for_idle)

    async def open_settings(self) -> StandardResponse:
        """通过命令面板打开设置页面。"""
        try:
            await self._cdp.dispatch_key_combo(["Control", "Shift", "KeyP"])
            await asyncio.sleep(1.5)
            json_cmd = json.dumps(">Settings: Open Settings")
            js = type_command_palette(json_cmd)
            await self._cdp.eval_js(js)
            await asyncio.sleep(1)
            await self._cdp.dispatch_key_combo(["Enter"])
            await asyncio.sleep(1)
            return StandardResponse(result=None, message="设置页面已打开", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"打开设置失败: {e}", code=-1)

    async def toggle_auto_mode(self, enable: bool = True) -> StandardResponse:
        """切换 SOLO 自动/手动模式。"""
        try:
            json_enable = "true" if enable else "false"
            js = toggle_auto_mode(SELECTORS["auto_mode_switch"], json_enable)
            result = await self._cdp.eval_js(js)
            return StandardResponse(result=result, message=f"自动模式: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"切换自动模式失败: {e}", code=-1)

    async def get_tasks(self) -> StandardResponse:
        """获取 SOLO 任务列表。"""
        try:
            js = query_tasks_detailed(SELECTORS)
            result = await self._cdp.eval_js(js)
            data = json.loads(result)
            return StandardResponse(result=data, message="任务列表", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"获取任务列表失败: {e}", code=-1)

    async def switch_task(self, task_index: int) -> StandardResponse:
        """切换到指定索引的任务。"""
        try:
            js = click_task_item(SELECTORS, task_index)
            result = await self._cdp.eval_js(js)
            return StandardResponse(result=result, message=f"切换任务: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"切换任务失败: {e}", code=-1)

    async def delete_current_task(self) -> StandardResponse:
        """删除当前任务。"""
        try:
            js = click_delete_task_btn(SELECTORS)
            result = await self._cdp.eval_js(js)
            await asyncio.sleep(0.5)
            await self.auto_confirm()
            return StandardResponse(result=result, message=f"删除任务: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"删除任务失败: {e}", code=-1)

    async def stop_generating(self) -> StandardResponse:
        """停止当前生成中的响应。
        生成中的发送按钮含 codicon-stop-circle 图标，点击即可停止。"""
        try:
            js = click_stop_btn()
            result = await self._cdp.eval_js(js)
            return StandardResponse(result=result, message=f"停止生成: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"停止生成失败: {e}", code=-1)

    async def open_file(self, file_path: str) -> StandardResponse:
        """在 Trae CN 中打开文件。"""
        try:
            json_path = json.dumps(file_path)
            await self._cdp.dispatch_key_combo(["Control", "KeyP"])
            await asyncio.sleep(1)
            js = type_quick_open(json_path)
            result = await self._cdp.eval_js(js)
            await asyncio.sleep(1)
            await self._cdp.dispatch_key_combo(["Enter"])
            return StandardResponse(result=result, message=f"打开文件: {file_path}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"打开文件失败: {e}", code=-1)
