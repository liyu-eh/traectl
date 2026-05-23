#!/usr/bin/env python3
"""MediaMixin — 截图等媒体操作：截图、重新生成、关闭对话框。"""

import asyncio
import base64
import json
import logging
import re
from datetime import datetime

from ..config import SELECTORS, CONSTANTS
from ..response import StandardResponse
from ..js_templates import (
    click_retry_btn,
    close_dialog_overlay,
    dispatch_escape_keydown,
    dispatch_escape_keyup,
    scan_dialogs,
    check_dialog_dismissed,
    click_overlay_button,
)


logger = logging.getLogger("traectl.controller")


class MediaMixin:
    """媒体操作 Mixin：截图、重新生成、关闭对话框。"""

    async def screenshot(self) -> StandardResponse:
        try:
            result = await self._cdp.capture_screenshot()
            return StandardResponse(result=result, message="截图", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"截图失败: {e}", code=-1)

    async def screenshot_to_file(self, output_path: str = None) -> StandardResponse:
        try:
            data = await self._cdp.capture_screenshot()
            if output_path is None:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = f"/tmp/trae_screenshot_{timestamp}.png"
            with open(output_path, "wb") as f:
                f.write(base64.b64decode(data))
            logger.info(f"截图已保存: {output_path}")
            return StandardResponse(result=output_path, message=f"截图已保存: {output_path}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"截图保存失败: {e}", code=-1)

    async def regenerate_last(self) -> StandardResponse:
        """点击最后一条回复的重试按钮，让 AI 重新生成。"""
        try:
            js = click_retry_btn()
            result = await self._cdp.eval_js(js)
            await asyncio.sleep(0.5)
            return StandardResponse(result=result, message=f"重新生成: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"重新生成失败: {e}", code=-1)

    async def close_dialog(self) -> StandardResponse:
        """关闭界面上弹出的对话框（优速通、模态框等）。"""
        try:
            js = close_dialog_overlay(SELECTORS["dialog_overlay"])
            result = await self._cdp.eval_js(js)
            if 'close' not in result.lower():
                await self._cdp.eval_js(dispatch_escape_keydown())
                await asyncio.sleep(0.05)
                await self._cdp.eval_js(dispatch_escape_keyup())
                result += ' + JS Escape'
            await asyncio.sleep(0.5)
            return StandardResponse(result=result, message=f"关闭对话框: {result}", code=0)
        except Exception as e:
            return StandardResponse(result=None, message=f"关闭对话框失败: {e}", code=-1)

    async def auto_handle_dialog(self) -> StandardResponse:
        """智能识别并自动处理页面弹窗，按类型执行对应操作。"""
        DIALOG_PATTERNS = CONSTANTS["DIALOG_PATTERNS"]
        MAX_RETRY = 3

        try:
            # 通过 CDP 扫描页面所有可见弹窗，提取文本内容
            scan_js = scan_dialogs()
            raw = await self._cdp.eval_js(scan_js)
            try:
                dialogs = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                dialogs = []

            if not dialogs:
                return StandardResponse(
                    result={"dialog_type": None, "action_taken": "none", "message": "无可见弹窗"},
                    message="无可见弹窗", code=0,
                )

            # 取第一个弹窗进行匹配
            dialog = dialogs[0]
            dialog_text = dialog.get("text", "")
            dialog_buttons = dialog.get("buttons", [])

            # 用 DIALOG_PATTERNS 正则匹配错误类型（匹配 pattern 最多的类型优先，更具体）
            matched_type = None
            best_match_count = 0
            for dtype, patterns in DIALOG_PATTERNS.items():
                match_count = sum(1 for p in patterns if re.search(p, dialog_text))
                if match_count > best_match_count:
                    best_match_count = match_count
                    matched_type = dtype

            # 按类型执行自动操作
            if matched_type in ("server_error", "error_2000000"):
                # 点「继续」按钮，3次失败则返回重启提示
                for attempt in range(1, MAX_RETRY + 1):
                    click_result = await self._click_dialog_button(
                        dialog_buttons, ["继续", "Continue", "重试", "Retry"],
                    )
                    if click_result:
                        await asyncio.sleep(1)
                        # 检查弹窗是否已消失
                        check = await self._cdp.eval_js(check_dialog_dismissed())
                        if check == "dismissed":
                            return StandardResponse(
                                result={"dialog_type": matched_type, "action_taken": "click-continue", "message": f"已点击继续按钮（第{attempt}次）"},
                                message=f"弹窗处理: {matched_type} → 点击继续（第{attempt}次）", code=0,
                            )
                return StandardResponse(
                    result={"dialog_type": matched_type, "action_taken": "retry-exhausted", "message": f"点击继续按钮{MAX_RETRY}次后弹窗仍在，建议重启"},
                    message=f"弹窗处理: {matched_type} → 重试{MAX_RETRY}次失败，建议重启", code=-1,
                )

            elif matched_type == "update_dialog":
                # 点「忽略」或「稍后」
                click_result = await self._click_dialog_button(
                    dialog_buttons, ["忽略", "稍后", "Ignore", "Later", "Skip", "跳过"],
                )
                action = "click-ignore" if click_result else "no-matching-button"
                msg = "已点击忽略/稍后" if click_result else "未找到忽略/稍后按钮"
                await asyncio.sleep(0.5)
                return StandardResponse(
                    result={"dialog_type": matched_type, "action_taken": action, "message": msg},
                    message=f"弹窗处理: {matched_type} → {msg}", code=0,
                )

            elif matched_type == "queue_reminder":
                # 读取排队位置号
                queue_match = re.search(r'排在第\s*(\d+)', dialog_text)
                position = queue_match.group(1) if queue_match else "未知"
                msg = f"排队中，位置: 第{position}位"
                await asyncio.sleep(0.5)
                return StandardResponse(
                    result={"dialog_type": matched_type, "action_taken": "queue-info", "message": msg, "position": position},
                    message=f"弹窗处理: {matched_type} → {msg}", code=0,
                )

            elif matched_type == "confirm_dialog":
                # 自动点「运行」
                click_result = await self._click_dialog_button(
                    dialog_buttons, ["运行", "Run", "确认", "确定", "Confirm", "OK"],
                )
                action = "click-run" if click_result else "no-matching-button"
                msg = "已点击运行" if click_result else "未找到运行按钮"
                await asyncio.sleep(0.5)
                return StandardResponse(
                    result={"dialog_type": matched_type, "action_taken": action, "message": msg},
                    message=f"弹窗处理: {matched_type} → {msg}", code=0,
                )

            else:
                # 未知弹窗 → 退回到 close_dialog 逻辑
                result = await self.close_dialog()
                return StandardResponse(
                    result={"dialog_type": "unknown", "action_taken": "close-dialog", "message": result.message},
                    message=f"弹窗处理: 未知类型 → {result.message}", code=result.code,
                )

        except Exception as e:
            return StandardResponse(result=None, message=f"智能弹窗处理失败: {e}", code=-1)

    async def _click_dialog_button(self, dialog_buttons: list[str], target_texts: list[str]) -> bool:
        """在弹窗按钮列表中查找目标文本并点击。返回是否成功点击。"""
        for target in target_texts:
            for btn_text in dialog_buttons:
                if target in btn_text:
                    js = click_overlay_button(target)
                    result = await self._cdp.eval_js(js)
                    if result:
                        return True
        return False
