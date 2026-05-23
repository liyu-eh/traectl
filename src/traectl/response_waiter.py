#!/usr/bin/env python3
"""ResponseWaiter — 等待 SOLO 响应的状态机。

从 chat_mixin.py 的 _wait_for_response 上帝方法重构而来，
将等待逻辑拆分为独立的状态机类，每个 tick 执行一次轮询。
"""

import asyncio
import logging
import os
import re
import time
from typing import Callable, Coroutine, Optional

from .config import CONSTANTS, SELECTORS, STABLE_THRESHOLD
from .js_templates import (
    check_is_generating,
    check_queue_status,
    click_confirm_btn,
    get_last_turn_role,
    get_queue_info,
    query_chat_content,
    query_chat_hash,
    query_solo_status,
    salvage_editor_text,
)
from .response import StandardResponse

logger = logging.getLogger("traectl.controller")


class ResponseWaiter:
    """等待 SOLO 响应的状态机。"""

    def __init__(
        self,
        cdp,
        workspace_root: str,
        progress_log: Optional[list[str]] = None,
        salvage_fn: Optional[Callable[[], Coroutine]] = None,
    ):
        self._cdp = cdp
        self._workspace_root = workspace_root
        self._progress_log = progress_log if progress_log is not None else []
        self._salvage_fn = salvage_fn
        self._last_heartbeat = -1
        self._stable_count = 0
        self._file_stable_count = 0
        self._last_hash = "initial"
        self._poll_count = 0
        self._saw_generating = False
        self._placeholder_confirm_count = 0
        self._last_mtimes: dict = {}
        self._mtime_report_interval = 0
        self._queue_reported = False

    # ── 主入口 ────────────────────────────────────────────────

    async def wait(self, timeout: int, max_retries: int = 3) -> StandardResponse:
        """主循环：等待响应完成。retry 循环包裹整个等待过程。"""
        for retry in range(max_retries):
            self._reset_state()
            start = time.monotonic()
            while (time.monotonic() - start) < timeout:
                wait = self._compute_poll_interval(self._poll_count)
                await asyncio.sleep(wait)
                try:
                    result = await self._tick(start, timeout)
                    if result is not None:
                        return result
                except Exception as e:
                    logger.warning(f"轮询异常: {e}")

            # 超时处理
            result = await self._handle_timeout(timeout, retry, max_retries)
            if result is not None:
                return result
            # 重试前等待
            if retry < max_retries - 1:
                await asyncio.sleep(2)

        return StandardResponse(
            result=None,
            message=CONSTANTS["TIMEOUT_FINAL_MSG"].format(timeout=timeout, max_retries=max_retries),
            code=-1,
        )

    # ── 状态重置 ──────────────────────────────────────────────

    def _reset_state(self):
        """重置状态（每次 retry 时调用）。"""
        self._stable_count = 0
        self._file_stable_count = 0
        self._last_hash = "initial"
        self._poll_count = 0
        self._saw_generating = False
        self._placeholder_confirm_count = 0
        self._last_mtimes = {}
        self._mtime_report_interval = 0
        self._queue_reported = False

    # ── 单次轮询 tick ────────────────────────────────────────

    async def _tick(self, start: float, timeout: int) -> Optional[StandardResponse]:
        """单次轮询 tick。返回 None 表示继续等待，返回 StandardResponse 表示完成。"""
        elapsed = time.monotonic() - start

        # 1. 自动确认检查
        confirmed, _ = await self._handle_auto_confirm()
        if confirmed:
            self._stable_count = 0
            self._last_hash = "initial"
            self._poll_count = 0
            return None

        # 2. 生成状态检测
        still_generating = await self._is_generating()
        if still_generating:
            if not self._saw_generating:
                self._saw_generating = True
                self._progress_log.append("[生成] SOLO 开始生成回复...")
            return None

        self._poll_count += 1

        # 3. 生成完成检测（最强信号）
        if self._check_generating_complete(self._saw_generating, still_generating):
            return await self._on_generating_done()

        # 4. 排队检测
        is_queued = await self._is_in_queue()
        if is_queued:
            return await self._on_queue(elapsed)

        # 5. 从未见过停止按钮且不在排队 → 开场白阶段
        if not self._saw_generating:
            if elapsed < 10 and self._poll_count < 5:
                # 心跳日志
                await self._log_heartbeat(elapsed)
                return None

        # 心跳日志
        await self._log_heartbeat(elapsed)

        # 6. 哈希稳定性检测（兜底）
        result = await self._check_hash_stability(timeout)
        if result is not None:
            return result

        # 7. 60% 超时提前返回
        result = await self._check_early_timeout(elapsed, timeout)
        if result is not None:
            return result

        # 8. "已做完"兜底
        result = await self._check_done_no_signal(elapsed, still_generating, is_queued)
        if result is not None:
            return result

        # 9. 文件 mtime 监控
        await self._monitor_files()

        return None

    # ── tick 子步骤 ───────────────────────────────────────────

    async def _on_generating_done(self) -> Optional[StandardResponse]:
        """saw_generating True→False：生成完成的最强信号。"""
        last_role = await self._get_last_turn_role()
        if last_role != "assistant":
            logger.info(f"saw_generating true→false 但最后角色是 {last_role}，等待新回复")
            self._saw_generating = False
            self._placeholder_confirm_count = 0
            return None
        content = await self.get_chat_content()
        content_text = content.result if content else ""
        if content_text and not self._is_placeholder(content_text):
            if self._is_folder_prompt(content_text):
                return StandardResponse(
                    result=None,
                    message="SOLO 要求打开文件夹。请在 Trae CN 中打开工作区文件夹后重试。",
                    code=-1,
                )
            progress = ""
            if self._progress_log:
                progress = "\n\n进度:\n" + "\n".join(self._progress_log[-3:])
            return StandardResponse(result=content_text, message=f"任务响应完成{progress}", code=0)
        # 内容是占位符，继续等待
        current_hash = await self._get_chat_hash()
        if current_hash and current_hash == self._last_hash and current_hash != "initial":
            self._placeholder_confirm_count += 1
        else:
            self._placeholder_confirm_count = 1
        if current_hash:
            self._last_hash = current_hash
        if self._placeholder_confirm_count >= 3:
            forced_content = await self.get_chat_content()
            forced_text = forced_content.result if forced_content else ""
            if forced_text and forced_text.strip():
                return StandardResponse(
                    result=forced_text, message="任务响应完成 (短内容强制返回)", code=0
                )
            self._saw_generating = False
            self._placeholder_confirm_count = 0
        return None

    async def _on_queue(self, elapsed: float) -> None:
        """排队中处理。返回 None 表示继续等待。"""
        if not self._queue_reported:
            self._queue_reported = True
            queue_info = await self._get_queue_info()
            self._progress_log.append(f"[排队] {queue_info}")
        # 排队中：每 30s 更新一次排队信息
        if int(elapsed) > 0 and int(elapsed) % 30 == 0 and self._last_heartbeat != int(elapsed) // 30:
            queue_info = await self._get_queue_info()
            self._progress_log.append(f"[排队] {queue_info}")
        return None

    async def _check_hash_stability(self, timeout: int) -> Optional[StandardResponse]:
        """哈希稳定检测（兜底：检测内容不再变化）。"""
        current_hash = await self._get_chat_hash()
        self._last_hash, self._stable_count, is_stable = self._detect_hash_stability(
            current_hash, self._last_hash, self._stable_count
        )

        if is_stable and self._saw_generating:
            content = await self.get_chat_content()
            content_text = content.result if content else ""
            if not self._is_placeholder(content_text):
                if self._is_folder_prompt(content_text):
                    return StandardResponse(
                        result=None,
                        message="SOLO 要求打开文件夹。请在 Trae CN 中打开工作区文件夹后重试。",
                        code=-1,
                    )
                progress = ""
                if self._progress_log:
                    progress = "\n\n进度:\n" + "\n".join(self._progress_log[-3:])
                return StandardResponse(result=content_text, message=f"任务响应完成{progress}", code=0)
            self._stable_count = 0

        return None

    async def _check_early_timeout(self, elapsed: float, timeout: int) -> Optional[StandardResponse]:
        """60% 超时提前返回。"""
        if self._stable_count >= 1 and self._saw_generating:
            elapsed_pct = elapsed / timeout
            if elapsed_pct > 0.6:
                content = await self.get_chat_content()
                content_text = content.result if content else ""
                if not self._is_placeholder(content_text):
                    progress = ""
                    if self._progress_log:
                        progress = "\n\n进度:\n" + "\n".join(self._progress_log[-3:])
                    return StandardResponse(
                        result=content_text, message=f"任务响应完成 (提前){progress}", code=0
                    )
                self._stable_count = 0
        return None

    async def _check_done_no_signal(
        self, elapsed: float, still_generating: bool, is_queued: bool
    ) -> Optional[StandardResponse]:
        """'已做完'兜底：从未见过生成信号，但已有内容。"""
        if not self._saw_generating and not still_generating and not is_queued and elapsed > 15:
            content = await self.get_chat_content()
            content_text = content.result if content else ""
            if content_text and not self._is_placeholder(content_text):
                last_role = await self._get_last_turn_role()
                if last_role == "assistant":
                    if self._is_folder_prompt(content_text):
                        return StandardResponse(
                            result=None,
                            message="SOLO 要求打开文件夹。请在 Trae CN 中打开工作区文件夹后重试。",
                            code=-1,
                        )
                    return StandardResponse(result=content_text, message="任务响应完成", code=0)
        return None

    async def _monitor_files(self):
        """文件 mtime 监控。"""
        changed = await self._monitor_file_mtime(self._workspace_root, self._last_mtimes)
        if changed:
            self._mtime_report_interval += 1
            self._file_stable_count = 0
            file_info = "; ".join(
                [f"{os.path.basename(k)} ({v['size']}B)" for k, v in changed.items()]
            )
            logger.info(f"文件变化: {file_info}")
            if self._mtime_report_interval % 3 == 0:
                self._progress_log.append(f"[文件] 文件变化: {file_info}")
        else:
            self._file_stable_count += 1

    async def _log_heartbeat(self, elapsed: float):
        """心跳日志。"""
        if int(elapsed) >= 15 and self._poll_count > 1 and self._last_heartbeat != int(elapsed) // 15:
            self._last_heartbeat = int(elapsed) // 15
            self._progress_log.append(f"[进度] 轮询#{self._poll_count}，已运行{elapsed:.0f}s")

    # ── 超时处理 ──────────────────────────────────────────────

    async def _handle_timeout(
        self, timeout: int, retry: int, max_retries: int
    ) -> Optional[StandardResponse]:
        """超时后尝试返回已有内容，否则返回 None 让外层重试。"""
        content = await self.get_chat_content()
        content_text = content.result if content else ""
        if content_text and content_text != CONSTANTS["NO_CHAT_CONTAINER"]:
            salvage = await self._salvage_editor_content()
            snapshot = await self._get_status_snapshot()
            timeout_msg = self._build_timeout_message(
                content_text, self._progress_log, salvage, snapshot
            )
            return StandardResponse(result=content_text, message=timeout_msg, code=-1)

        logger.warning(
            CONSTANTS["TIMEOUT_EMPTY_RETRY_MSG"].format(retry=retry + 1, max_retries=max_retries)
        )
        return None

    # ── CDP 交互方法 ──────────────────────────────────────────

    async def get_chat_content(self, max_length: int = 5000) -> StandardResponse:
        """获取聊天记录。"""
        js = query_chat_content(SELECTORS, max_length, CONSTANTS)
        result = await self._cdp.eval_js(js)
        return StandardResponse(result=result, message="聊天内容", code=0)

    async def _get_chat_hash(self) -> str:
        """获取聊天内容的哈希（用于稳定检测）。"""
        js = query_chat_hash(SELECTORS)
        return await self._cdp.eval_js(js)

    async def auto_confirm(self) -> StandardResponse:
        """自动确认处理。"""
        js = click_confirm_btn(SELECTORS["inline_delete"])
        result = await self._cdp.eval_js(js)
        return StandardResponse(result=result, message=f"自动确认: {result}", code=0)

    async def _handle_auto_confirm(self) -> tuple[bool, str]:
        """自动确认处理。返回 (confirmed, result)。"""
        confirm_result = await self.auto_confirm()
        confirmed_text = confirm_result.result if hasattr(confirm_result, 'result') else str(confirm_result)
        if "confirmed" in str(confirmed_text):
            await asyncio.sleep(2)
            return True, confirm_result
        return False, confirm_result

    async def _is_in_queue(self) -> bool:
        """检测 SOLO 是否在排队等待。"""
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
            if result in ("user", "assistant"):
                return result
            return ""
        except Exception:
            return ""

    async def _is_generating(self) -> bool:
        """检查 SOLO 是否正在生成回复。"""
        try:
            js = check_is_generating()
            result = await self._cdp.eval_js(js)
            return result is True or result == "true"
        except Exception as e:
            logger.debug(f"_is_generating 异常: {e}")
            return False

    async def _get_status_snapshot(self) -> str:
        """获取 SOLO 面板状态快照。"""
        try:
            js = query_solo_status(SELECTORS)
            result = await self._cdp.eval_js(js)
            import json
            try:
                json.loads(result)
            except (json.JSONDecodeError, TypeError):
                pass
            return f"\n\n[面板快照]\n{result}"
        except Exception:
            return ""

    async def _salvage_editor_content(self) -> str:
        """超时时通过 CDP 检查编辑器是否有未保存的半成品代码。"""
        if self._salvage_fn is not None:
            return await self._salvage_fn()
        js = salvage_editor_text()
        try:
            content = await self._cdp.eval_js(js)
            if content and len(content) > 100:
                return f"\n\n[CDP 编辑器半成品]\n```\n{content}\n```"
            return ""
        except Exception:
            return ""

    async def _monitor_file_mtime(self, dir_path: str, last_mtimes: dict) -> dict:
        """轮询检查文件 mtime 变化。返回最新的文件状态快照。"""
        import glob as _glob

        changed = {}
        try:
            for f in (
                _glob.glob(os.path.join(dir_path, "*.html"))
                + _glob.glob(os.path.join(dir_path, "*.py"))
                + _glob.glob(os.path.join(dir_path, "*.js"))
                + _glob.glob(os.path.join(dir_path, "*.css"))
            ):
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

    # ── 纯函数 / 静态方法 ─────────────────────────────────────

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

    @staticmethod
    def _normalize_content(content: str) -> str:
        if not content:
            return ""
        content = re.sub(r" +", " ", content)
        content = re.sub(r"\n+", "\n", content)
        return content.strip()

    @staticmethod
    def _is_placeholder(content: str) -> bool:
        """检测是否为占位符内容（如"正在分析问题..."），等待真实回复。"""
        if not content:
            return True
        progress_kw = CONSTANTS["PROGRESS_KEYWORDS"]
        stripped = content.rstrip()
        if stripped and stripped[-1] in "。！？":
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
        lines = [l.strip() for l in content.split("\n") if l.strip()]
        if lines:
            last_line = lines[-1]
            if len(last_line) < 50 and (last_line.endswith("..") or last_line.endswith("...")):
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
