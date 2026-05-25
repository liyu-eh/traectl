#!/usr/bin/env python3
"""ModelMixin 测试：模型获取、列表、切换。

全部 Mock，不需要真实 Trae CN/CDP。
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from traectl.response import StandardResponse
from traectl.config import SELECTORS, CDP_HOST, CDP_PORT


# ── 辅助函数 ──────────────────────────────────────────────

def _make_controller():
    """创建一个绑定了 mock _cdp 的 TraeSoloController。"""
    from traectl.controller import TraeSoloController
    from traectl.cdp_client import CDPClient

    cdp = MagicMock(spec=CDPClient)
    cdp.eval_js = AsyncMock(return_value="")
    cdp.host = CDP_HOST
    cdp.port = CDP_PORT

    controller = TraeSoloController(cdp)
    return controller, cdp


# ══════════════════════════════════════════════════════════
# get_current_model
# ══════════════════════════════════════════════════════════

class TestGetCurrentModel:
    def test_returns_model_name(self):
        ctrl, cdp = _make_controller()
        cdp.eval_js.return_value = "DeepSeek-V4-Pro"

        async def _run():
            resp = await ctrl.get_current_model()
            assert resp.code == 0
            assert resp.result == "DeepSeek-V4-Pro"
        import asyncio
        asyncio.run(_run())

    def test_unknown_when_eval_js_none(self):
        ctrl, cdp = _make_controller()
        cdp.eval_js.return_value = None

        async def _run():
            resp = await ctrl.get_current_model()
            assert resp.result == "unknown"
        import asyncio
        asyncio.run(_run())

    def test_uses_correct_selector(self):
        ctrl, cdp = _make_controller()

        async def _run():
            await ctrl.get_current_model()
            js = cdp.eval_js.call_args[0][0]
            assert SELECTORS["model_trigger_value"] in js
        import asyncio
        asyncio.run(_run())


# ══════════════════════════════════════════════════════════
# list_models
# ══════════════════════════════════════════════════════════

class TestListModels:
    @pytest.mark.asyncio
    async def test_returns_available_models(self):
        ctrl, cdp = _make_controller()
        model_data = [
            {"name": "DeepSeek-V4-Pro", "selected": True},
            {"name": "Kimi-K2.6", "selected": False},
        ]

        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=True)), \
             patch.object(ctrl, '_close_model_selector', new=AsyncMock()):

            cdp.eval_js.side_effect = [
                "5",                     # count_model_items — list_models 内部的轮询
                json.dumps(model_data),  # query_model_list
            ]

            resp = await ctrl.list_models()
            assert resp.code == 0
            assert len(resp.result) == 2
            assert resp.result[0]["name"] == "DeepSeek-V4-Pro"

    @pytest.mark.asyncio
    async def test_cannot_open_selector(self):
        ctrl, cdp = _make_controller()
        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=False)):
            ctrl.get_current_model = AsyncMock(
                return_value=StandardResponse(result="current-model", message="", code=0)
            )
            resp = await ctrl.list_models()
            assert resp.code == -1
            assert "无法打开模型选择器" in resp.message

    @pytest.mark.asyncio
    async def test_json_parse_error(self):
        ctrl, cdp = _make_controller()
        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=True)), \
             patch.object(ctrl, '_close_model_selector', new=AsyncMock()):
            cdp.eval_js.side_effect = ["5", "not-json"]
            resp = await ctrl.list_models()
            assert resp.code == -1
            assert "解析失败" in resp.message


# ══════════════════════════════════════════════════════════
# switch_model
# ══════════════════════════════════════════════════════════

class TestSwitchModel:
    @pytest.mark.asyncio
    async def test_already_current_model(self):
        """已是目标模型 → 立即返回，不做任何操作。"""
        ctrl, cdp = _make_controller()
        ctrl.get_current_model = AsyncMock(
            return_value=StandardResponse(result="DeepSeek-V4-Pro", message="", code=0)
        )

        resp = await ctrl.switch_model("DeepSeek-V4-Pro")
        assert resp.code == 0
        assert "已是" in resp.message

    @pytest.mark.asyncio
    async def test_switch_success(self):
        ctrl, cdp = _make_controller()
        ctrl.get_current_model = AsyncMock(side_effect=[
            StandardResponse(result="Kimi-K2.6", message="", code=0),
            StandardResponse(result="DeepSeek-V4-Pro", message="", code=0),
        ])

        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=True)):
            cdp.eval_js.side_effect = ["10", True]

            resp = await ctrl.switch_model("DeepSeek-V4-Pro")
            assert resp.code == 0
            assert resp.result["from"] == "Kimi-K2.6"
            assert resp.result["to"] == "DeepSeek-V4-Pro"

    @pytest.mark.asyncio
    async def test_switch_selector_open_fails(self):
        ctrl, cdp = _make_controller()
        ctrl.get_current_model = AsyncMock(
            return_value=StandardResponse(result="Kimi-K2.6", message="", code=0)
        )

        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=False)):
            resp = await ctrl.switch_model("DeepSeek-V4-Pro")
            assert resp.code == -1
            assert "无法打开模型选择器" in resp.message

    @pytest.mark.asyncio
    async def test_switch_model_mismatch(self):
        """切换后模型不匹配期望。"""
        ctrl, cdp = _make_controller()
        ctrl.get_current_model = AsyncMock(side_effect=[
            StandardResponse(result="Kimi-K2.6", message="", code=0),
            StandardResponse(result="Still-Kimi", message="", code=0),
        ])

        with patch.object(ctrl, '_open_model_selector', new=AsyncMock(return_value=True)):
            cdp.eval_js.side_effect = ["10", True]

            resp = await ctrl.switch_model("DeepSeek-V4-Pro")
            assert resp.code == -1
            assert "切换结果不确定" in resp.message


# ══════════════════════════════════════════════════════════
# _model_name_match（模糊匹配）
# ══════════════════════════════════════════════════════════

class TestModelNameMatch:
    def _match(self, requested: str, displayed: str) -> bool:
        from traectl.mixins.chat_mixin import ChatMixin
        return ChatMixin._model_name_match(requested, displayed)

    @pytest.mark.parametrize("requested,displayed,expected", [
        ("DeepSeek-V4-Pro",   "DeepSeek-V4-Pro",    True),   # exact
        ("DeepSeek-V4",       "DeepSeek-V4 Beta",   True),   # beta stripped
        ("DeepSeek-V4 Beta",  "DeepSeek-V4",        True),   # beta stripped reverse
        ("GPT-4",             "DeepSeek-V4-Pro",    False),  # different model
        ("DeepSeek",          "",                    False),  # empty displayed
        ("",                  "",                    True),   # both empty
    ])
    def test_model_name_match(self, requested, displayed, expected):
        from traectl.mixins.chat_mixin import ChatMixin
        assert ChatMixin._model_name_match(requested, displayed) is expected


# ══════════════════════════════════════════════════════════
# _open_model_selector（重试策略）
# ══════════════════════════════════════════════════════════

# 辅助：生成 _open_model_selector 所需的 eval_js 返回值序列
def _open_selector_results(success_on_attempt=0):
    """
    生成 eval_js side_effect 的返回值序列。
    
    每轮尝试：
      - 1x body.click() → None
      - 1x trigger → None  
      - 17x count → 全部 "0" 直到 success_on_attempt 时返回 "5"
      - 1x trigger_js → None
      - 17x count → 同上
    
    success_on_attempt: 在第几次尝试成功（0=永不, 1/2/3）
    """
    results = []
    for attempt in range(1, 4):
        # Mouse route
        results.append(None)  # body.click
        results.append(None)  # trigger
        for p in range(17):
            if attempt == success_on_attempt and p >= 3:  # 第4次轮询返回
                results.append("5")
                return results
            results.append("0")

        # JS route
        results.append(None)  # trigger_js
        for p in range(17):
            if attempt == success_on_attempt:
                results.append("5")
                return results
            results.append("0")

    return results


class TestOpenModelSelector:
    @pytest.mark.asyncio
    async def test_first_mouse_event_success(self):
        ctrl, cdp = _make_controller()

        results = _open_selector_results(success_on_attempt=1)
        cdp.eval_js.side_effect = results

        result = await ctrl._open_model_selector()
        assert result is True

    @pytest.mark.asyncio
    async def test_mouse_fails_js_succeeds(self):
        ctrl, cdp = _make_controller()
        # attempt 1: mouse fails (all 17 count=0), JS succeeds
        results = []
        # attempt 1 mouse route
        results.append(None)  # body.click
        results.append(None)  # trigger
        results.extend(["0"] * 17)
        # attempt 1 JS route — 5th poll succeeds
        results.append(None)  # trigger_js
        results.extend(["0", "0", "0", "0", "5"])

        cdp.eval_js.side_effect = results

        result = await ctrl._open_model_selector()
        assert result is True

    @pytest.mark.asyncio
    async def test_all_attempts_exhausted(self):
        ctrl, cdp = _make_controller()
        results = _open_selector_results(success_on_attempt=0)
        cdp.eval_js.side_effect = results

        result = await ctrl._open_model_selector()
        assert result is False

    @pytest.mark.asyncio
    async def test_success_on_second_attempt(self):
        ctrl, cdp = _make_controller()
        results = _open_selector_results(success_on_attempt=2)
        cdp.eval_js.side_effect = results

        result = await ctrl._open_model_selector()
        assert result is True
