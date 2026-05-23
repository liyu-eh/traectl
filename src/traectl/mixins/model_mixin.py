#!/usr/bin/env python3
"""ModelMixin — 模型管理：获取、列表、切换模型。"""

import asyncio
import json
import logging

from ..config import SELECTORS
from ..response import StandardResponse
from ..js_templates import (
    query_current_model,
    count_model_items,
    query_model_list,
    click_model_item,
    trigger_model_selector,
    trigger_model_selector_js,
)


logger = logging.getLogger("traectl.controller")


class ModelMixin:
    """模型管理 Mixin：获取当前模型、列出可用模型、切换模型。"""

    async def get_current_model(self) -> StandardResponse:
        js = query_current_model(SELECTORS["model_trigger_value"])
        result = (await self._cdp.eval_js(js)) or "unknown"
        return StandardResponse(result=result, message=f"当前模型: {result}", code=0)

    async def list_models(self) -> StandardResponse:
        """获取所有可用模型列表。需要打开选择器读取。"""
        opened = await self._open_model_selector()
        if not opened:
            current_resp = await self.get_current_model()
            return StandardResponse(
                result={
                    "error": "无法打开模型选择器",
                    "availableModels": [],
                    "currentModel": current_resp.result,
                },
                message="无法打开模型选择器",
                code=-1,
            )

        for attempt in range(5):
            count = await self._cdp.eval_js(count_model_items(SELECTORS["model_item"]))
            if count and int(count) > 0:
                break
            logger.info(f"list_models: 等待列表渲染 (attempt {attempt + 1})")
            await asyncio.sleep(1)

        result = await self._cdp.eval_js(query_model_list(SELECTORS))
        await self._close_model_selector()
        try:
            data = json.loads(result)
            return StandardResponse(result=data, message="模型列表", code=0)
        except (json.JSONDecodeError, TypeError):
            return StandardResponse(result=result, message="模型列表解析失败", code=-1)

    async def switch_model(self, model_name: str) -> StandardResponse:
        """切换 SOLO 模型。"""
        current_resp = await self.get_current_model()
        current = current_resp.result
        if current == model_name:
            return StandardResponse(result=current, message=f"模型已是 {model_name}，无需切换", code=0)

        opened = await self._open_model_selector()
        if not opened:
            return StandardResponse(result=None, message=f"无法打开模型选择器，无法切换到 {model_name}", code=-1)

        for poll in range(17):
            check = await self._cdp.eval_js(count_model_items(SELECTORS["model_item"]))
            if check and int(check) > 0:
                break
            await asyncio.sleep(0.3)

        json_name = json.dumps(model_name)
        js = click_model_item(SELECTORS, json_name)
        result = await self._cdp.eval_js(js)
        await asyncio.sleep(1)

        new_model_resp = await self.get_current_model()
        new_model = new_model_resp.result
        if self._model_name_match(model_name, new_model):
            return StandardResponse(
                result={"from": current, "to": new_model},
                message=f"模型切换成功: {current} → {new_model}",
                code=0,
            )
        return StandardResponse(
            result={"expected": model_name, "current": new_model, "js_result": result},
            message=f"切换结果不确定: 期望 {model_name}, 当前 {new_model}",
            code=-1,
        )

    async def _open_model_selector(self) -> bool:
        """用 CDP 鼠标事件打开模型选择器下拉。"""
        for attempt in range(3):
            await self._cdp.eval_js("document.body.click()")
            await asyncio.sleep(0.5)

            await self._cdp.eval_js(trigger_model_selector(SELECTORS["model_trigger"]))

            for poll in range(17):
                await asyncio.sleep(0.3)
                check = await self._cdp.eval_js(count_model_items(SELECTORS["model_item"]))
                if check and int(check) > 0:
                    logger.info(f"模型选择器已打开，{check} 个模型")
                    return True

            logger.info(f"Mouse event failed, trying JS trigger (attempt {attempt + 1}/3)")
            await self._cdp.eval_js(trigger_model_selector_js())

            for poll in range(17):
                await asyncio.sleep(0.3)
                check = await self._cdp.eval_js(count_model_items(SELECTORS["model_item"]))
                if check and int(check) > 0:
                    logger.info(f"模型选择器通过 JS 事件已打开")
                    return True

        logger.warning("模型选择器 3 次尝试均未渲染")
        return False

    async def _close_model_selector(self) -> None:
        await self._cdp.eval_js("document.body.click()")
