#!/usr/bin/env python3
"""ChatMixin — 基础交互：聊天、消息、状态检测。"""

import asyncio
import json
import logging
import re
import os

from ..config import (
    CONSTANTS,
    SELECTORS,
    STABLE_THRESHOLD,
)
from ..js_templates import (
    click_new_task_btn,
    focus_input_box,
    verify_input_text,
    click_send_btn,
    query_chat_content,
    query_chat_hash,
    query_solo_status,
    query_task_list,
    click_confirm_btn,
    check_queue_status,
    get_queue_info,
    get_last_turn_role,
    check_is_generating,
)
from ..response import StandardResponse
from ..response_waiter import ResponseWaiter


logger = logging.getLogger("traectl.controller")


class ChatMixin:
    """基础交互 Mixin：聊天消息、状态检测、等待响应。"""

    async def start_new_task(self) -> StandardResponse:
        js = click_new_task_btn(SELECTORS["new_task_btn"])
        result = await self._cdp.eval_js(js)
        await asyncio.sleep(1)
        ok = "clicked" in result
        return StandardResponse(result=result, message=f"新任务: {result}", code=0 if ok else -1)

    async def type_message(self, text: str) -> StandardResponse:
        """使用 CDP Input.insertText 输入文本（React contenteditable 唯一可靠方案）。"""
        json_text = json.dumps(text)
        js = focus_input_box(SELECTORS["input_box"])
        await self._cdp.eval_js(js)
        await asyncio.sleep(0.2)
        # 使用 CDP Input.insertText 输入文本（不受 JS 状态机影响）
        await self._cdp.insert_text(text)
        await asyncio.sleep(0.3)
        verify = await self._cdp.eval_js(verify_input_text(SELECTORS["input_box"]))
        msg = f"inserted (len={len(text)}): {verify}"
        return StandardResponse(result=msg, message=f"输入: {msg}", code=0)

    async def send_message(self) -> StandardResponse:
        js = click_send_btn(SELECTORS["send_btn"])
        result = await self._cdp.eval_js(js)
        ok = result == "sent"
        return StandardResponse(result=result, message=f"发送: {result}", code=0 if ok else -1)

    async def get_chat_content(self, max_length: int = 5000) -> StandardResponse:
        """获取聊天记录。只提取真实消息内容（不包含面板状态文字）。
        当前 Trae CN DOM 结构：
        - user: section[data-role="user"] > div.icube-value > div.value
        - assistant: section[data-role="assistant"] > div.assistant-chat-turn-content
        """
        js = query_chat_content(SELECTORS, max_length, CONSTANTS)
        result = await self._cdp.eval_js(js)
        return StandardResponse(result=result, message="聊天内容", code=0)

    async def _get_chat_hash(self) -> str:
        """获取聊天内容的哈希（用于稳定检测）。使用与 get_chat_content 相同的 DOM 查询。"""
        js = query_chat_hash(SELECTORS)
        return await self._cdp.eval_js(js)

    async def get_solo_status(self) -> StandardResponse:
        js = query_solo_status(SELECTORS)
        result = await self._cdp.eval_js(js)
        try:
            data = json.loads(result)
            return StandardResponse(result=data, message="SOLO 状态", code=0)
        except (json.JSONDecodeError, TypeError):
            return StandardResponse(result=result, message=f"SOLO 状态解析失败: {result}", code=-1)

    async def get_task_list(self) -> StandardResponse:
        js = query_task_list(SELECTORS)
        result = await self._cdp.eval_js(js)
        try:
            data = json.loads(result)
            return StandardResponse(result=data, message="任务列表", code=0)
        except (json.JSONDecodeError, TypeError):
            return StandardResponse(result=result, message=f"任务列表解析失败", code=-1)

    async def auto_confirm(self) -> StandardResponse:
        js = click_confirm_btn(SELECTORS["inline_delete"])
        result = await self._cdp.eval_js(js)
        return StandardResponse(result=result, message=f"自动确认: {result}", code=0)

    async def _wait_for_response(self, timeout: int, max_retries: int = 3) -> StandardResponse:
        """等待 SOLO 响应，委托给 ResponseWaiter 状态机。"""
        if not hasattr(self, '_progress_log'):
            self._progress_log = []
        waiter = ResponseWaiter(
            self._cdp,
            self._workspace_root,
            self._progress_log,
            salvage_fn=self._salvage_editor_content,
        )
        return await waiter.wait(timeout, max_retries)

    async def _is_in_queue(self) -> bool:
        """检测 SOLO 是否在排队等待（而非真正生成中）。"""
        try:
            js = check_queue_status()
            result = await self._cdp.eval_js(js)
            return result is True or result == "true"
        except Exception:
            return False

    async def _get_queue_info(self) -> str:
        """获取排队信息摘要。"""
        try:
            js = get_queue_info(CONSTANTS["QUEUE_INFO_FALLBACK"])
            return await self._cdp.eval_js(js) or CONSTANTS["QUEUE_INFO_FALLBACK"]
        except Exception:
            return CONSTANTS["QUEUE_INFO_FALLBACK"]

    async def _get_last_turn_role(self) -> str:
        """获取最后一条发言的角色。返回 'user', 'assistant' 或 ''。"""
        try:
            js = get_last_turn_role()
            result = await self._cdp.eval_js(js)
            if result in ('user', 'assistant'):
                return result
            return ''
        except Exception:
            return ''

    async def _is_generating(self) -> bool:
        """检查 SOLO 是否正在生成回复。
        当前 Trae CN 版本的停止按钮就是发送按钮本身——生成中发送按钮的图标变为停止图标。
        - 生成中：.chat-input-v2-send-button disabled=false + 内部 codicon-stop-circle 可见
        - 空闲无内容：发送按钮 disabled=true
        - 排队中：alert 或最后一条 assistant 消息包含排队提醒，不算 generating"""
        try:
            js = check_is_generating()
            result = await self._cdp.eval_js(js)
            return result is True or result == "true"
        except Exception as e:
            logger.debug(f"_is_generating 异常: {e}")
            return False

    @staticmethod
    def _normalize_content(content: str) -> str:
        if not content:
            return ""
        content = re.sub(r' +', ' ', content)
        content = re.sub(r'\n+', '\n', content)
        return content.strip()

    @staticmethod
    def _is_placeholder(content: str) -> bool:
        """检测是否为占位符内容（如"正在分析问题..."），等待真实回复。"""
        if not content:
            return True
        progress_kw = CONSTANTS["PROGRESS_KEYWORDS"]
        stripped = content.rstrip()
        if stripped and stripped[-1] in '。！？':
            for p in progress_kw:
                if p in content:
                    return True
            return False
        if len(content) < 20:
            for p in progress_kw:
                if p in content:
                    return True
            return False
        if len(content) < 60:
            for p in progress_kw:
                if p in content:
                    return True
            return False
        for p in progress_kw:
            if p in content:
                return True
        queue_kw = CONSTANTS["QUEUE_KEYWORDS"]
        for q in queue_kw:
            if q in content:
                return True
        if len(content) < 300:
            status_indicators = CONSTANTS["STATUS_INDICATORS"]
            match_count = sum(1 for s in status_indicators if s in content)
            if match_count >= 2:
                return True
        lines = [l.strip() for l in content.split('\n') if l.strip()]
        if lines:
            last_line = lines[-1]
            if len(last_line) < 50 and (last_line.endswith('..') or last_line.endswith('...')):
                if any(p in last_line for p in progress_kw):
                    return True
        return False

    @staticmethod
    def _is_folder_prompt(content: str) -> bool:
        markers = CONSTANTS["FOLDER_PROMPT_MARKERS"]
        return all(m in content for m in markers)

    @staticmethod
    def _model_name_match(requested: str, displayed: str) -> bool:
        if requested == displayed:
            return True
        strip = lambda n: n.replace("Beta", "").rstrip()
        return strip(requested) == strip(displayed)

    async def _get_status_snapshot(self) -> str:
        """获取 SOLO 面板状态快照。"""
        try:
            status = await self.get_solo_status()
            return f"\n\n[面板快照]\n{status}"
        except Exception:
            return ""

    async def _monitor_file_mtime(self, dir_path: str, last_mtimes: dict) -> dict:
        """轮询检查文件 mtime 变化。返回最新的文件状态快照。"""
        import glob as _glob
        changed = {}
        try:
            for f in _glob.glob(os.path.join(dir_path, "*.html")) + _glob.glob(os.path.join(dir_path, "*.py")) + _glob.glob(os.path.join(dir_path, "*.js")) + _glob.glob(os.path.join(dir_path, "*.css")):
                try:
                    mtime = os.path.getmtime(f)
                    old = last_mtimes.get(f, 0)
                    if mtime > old:
                        changed[f] = {"mtime": mtime, "size": os.path.getsize(f)}
                        last_mtimes[f] = mtime
                except OSError:
                    pass
        except Exception:
            pass
        return changed

    @staticmethod
    def _compute_poll_interval(poll_count: int) -> float:
        """根据轮询次数计算等待间隔（0.5→1.0→2.0→5.0）。"""
        if poll_count < 5:
            return 0.5
        elif poll_count < 10:
            return 1.0
        elif poll_count < 20:
            return 2.0
        else:
            return 5.0

    async def _handle_auto_confirm(self) -> tuple[bool, str]:
        """自动确认处理。返回 (confirmed, result)。"""
        confirm_result = await self.auto_confirm()
        if "confirmed" in confirm_result:
            await asyncio.sleep(2)
            return True, confirm_result
        return False, confirm_result

    @staticmethod
    def _check_generating_complete(saw_generating: bool, still_generating: bool) -> bool:
        """检测生成结束信号：saw_generating True→False。"""
        return saw_generating and not still_generating

    @staticmethod
    def _detect_hash_stability(
        current_hash: str, last_hash: str, stable_count: int
    ) -> tuple[str, int, bool]:
        """hash 稳定性检测。返回 (new_last_hash, new_stable_count, is_stable)。"""
        if current_hash and current_hash == last_hash and current_hash != "initial":
            new_stable = stable_count + 1
        else:
            new_stable = 0
        new_last = current_hash if current_hash else last_hash
        is_stable = new_stable >= STABLE_THRESHOLD
        return new_last, new_stable, is_stable

    def _build_timeout_message(
        self, content: str, progress_log: list[str], salvage: str, snapshot: str
    ) -> str:
        """组装超时返回消息。"""
        progress = ""
        if progress_log:
            progress = "\n".join(progress_log[-5:]) + "\n\n"
        return CONSTANTS["TIMEOUT_MSG_TEMPLATE"].format(
            timeout=0, progress=progress, content=content, salvage=salvage, snapshot=snapshot
        )
