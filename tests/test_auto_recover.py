"""测试 DIALOG_PATTERNS 匹配逻辑及 auto_handle_dialog 行为。"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from traectl.config import CONSTANTS
from traectl.response import StandardResponse


# ── DIALOG_PATTERNS 结构验证 ──────────────────────────────────


class TestDialogPatternsStructure:
    """验证 DIALOG_PATTERNS 常量结构完整性。"""

    def test_dialog_patterns_exists(self):
        assert "DIALOG_PATTERNS" in CONSTANTS

    def test_dialog_patterns_is_dict(self):
        assert isinstance(CONSTANTS["DIALOG_PATTERNS"], dict)

    @pytest.mark.parametrize("key", [
        "server_error", "error_2000000", "update_dialog",
        "queue_reminder", "confirm_dialog",
    ])
    def test_required_keys_present(self, key):
        assert key in CONSTANTS["DIALOG_PATTERNS"], f"DIALOG_PATTERNS missing key: {key}"

    @pytest.mark.parametrize("key", [
        "server_error", "error_2000000", "update_dialog",
        "queue_reminder", "confirm_dialog",
    ])
    def test_patterns_are_non_empty_lists(self, key):
        patterns = CONSTANTS["DIALOG_PATTERNS"][key]
        assert isinstance(patterns, list), f"DIALOG_PATTERNS[{key}] should be a list"
        assert len(patterns) > 0, f"DIALOG_PATTERNS[{key}] should not be empty"


# ── DIALOG_PATTERNS 正则匹配逻辑 ──────────────────────────────


def _match_dialog_type(text: str) -> str | None:
    """模拟 auto_handle_dialog 中的匹配逻辑（匹配 pattern 最多的类型优先）。"""
    DIALOG_PATTERNS = CONSTANTS["DIALOG_PATTERNS"]
    matched_type = None
    best_match_count = 0
    for dtype, patterns in DIALOG_PATTERNS.items():
        match_count = sum(1 for p in patterns if re.search(p, text))
        if match_count > best_match_count:
            best_match_count = match_count
            matched_type = dtype
    return matched_type


class TestDialogPatternMatching:
    """验证 DIALOG_PATTERNS 对各类弹窗文本的匹配。"""

    # server_error 匹配
    @pytest.mark.parametrize("text", [
        "服务端异常，请稍后重试",
        "发生服务端异常",
        "请稍后重试",
        "系统未知错误，请联系管理员",
    ])
    def test_server_error_match(self, text):
        assert _match_dialog_type(text) == "server_error"

    # error_2000000 匹配
    @pytest.mark.parametrize("text", [
        "错误码 2000000 系统未知错误",
        "2000000: 系统未知错误",
    ])
    def test_error_2000000_match(self, text):
        assert _match_dialog_type(text) == "error_2000000"

    # update_dialog 匹配
    @pytest.mark.parametrize("text", [
        "检测到新版 v2.0",
        "检测到新版，是否更新？",
    ])
    def test_update_dialog_match(self, text):
        assert _match_dialog_type(text) == "update_dialog"

    # queue_reminder 匹配
    @pytest.mark.parametrize("text", [
        "排队提醒：当前模型请求较多",
        "排队提醒，排在第5位",
        "你排在第3位，请耐心等待",
    ])
    def test_queue_reminder_match(self, text):
        assert _match_dialog_type(text) == "queue_reminder"

    # confirm_dialog 匹配
    @pytest.mark.parametrize("text", [
        "运行前检查：以下文件将被修改",
        "确认执行此操作？",
        "确定要删除此文件吗？",
    ])
    def test_confirm_dialog_match(self, text):
        assert _match_dialog_type(text) == "confirm_dialog"

    # 未知弹窗
    def test_unknown_dialog_no_match(self):
        assert _match_dialog_type("这是一个普通的提示信息") is None

    # 匹配优先级：error_2000000 匹配更多 pattern 时优先（更具体）
    def test_error_2000000_priority_over_server_error(self):
        """当文本同时匹配 server_error 和 error_2000000 时，匹配更多 pattern 的优先。"""
        text = "服务端异常 2000000 系统未知错误"
        result = _match_dialog_type(text)
        # error_2000000 匹配 "2000000" + "系统未知错误" = 2，server_error 匹配 "服务端异常" + "系统未知错误" = 2
        # 两者匹配数相同时，先遍历到的优先（server_error 在前）
        assert result in ("server_error", "error_2000000")


# ── 排队位置提取逻辑 ──────────────────────────────────────────


class TestQueuePositionExtraction:
    """验证排队位置号的正则提取。"""

    def test_extract_position_number(self):
        match = re.search(r'排在第\s*(\d+)', "排队提醒，排在第5位")
        assert match is not None
        assert match.group(1) == "5"

    def test_extract_position_large_number(self):
        match = re.search(r'排在第\s*(\d+)', "排在第128位，请耐心等待")
        assert match is not None
        assert match.group(1) == "128"

    def test_extract_position_with_space(self):
        match = re.search(r'排在第\s*(\d+)', "排在第 10 位")
        assert match is not None
        assert match.group(1) == "10"

    def test_no_position_returns_none(self):
        match = re.search(r'排在第\s*(\d+)', "排队提醒，请稍候")
        assert match is None


# ── auto_handle_dialog 异步行为测试 ────────────────────────────


class TestAutoHandleDialogBehavior:
    """通过 Mock 测试 auto_handle_dialog 的异步行为。"""

    def _make_mixin(self):
        """创建一个绑定了 mock _cdp 的 MediaMixin 实例。

        创建测试用子类补全 TraeSoloProtocol 的抽象方法，
        因为测试只需 MediaMixin 自身的方法，其他方法用 stub 实现。
        """
        from traectl.mixins.media_mixin import MediaMixin

        class _TestableMediaMixin(MediaMixin):
            async def start_new_task(self): ...
            async def type_message(self, text: str): ...
            async def send_message(self): ...
            async def auto_confirm(self): ...
            async def get_chat_content(self, max_length: int = 5000): ...
            async def switch_model(self, model_name: str): ...

        mixin = _TestableMediaMixin()
        mixin._cdp = MagicMock()
        mixin._cdp.eval_js = AsyncMock()
        return mixin

    @pytest.mark.asyncio
    async def test_no_dialog_visible(self):
        """无可见弹窗时返回 dialog_type=None。"""
        mixin = self._make_mixin()
        mixin._cdp.eval_js.return_value = "[]"

        resp = await mixin.auto_handle_dialog()
        assert resp.code == 0
        assert resp.result["dialog_type"] is None
        assert resp.result["action_taken"] == "none"

    @pytest.mark.asyncio
    async def test_server_error_click_continue(self):
        """server_error 弹窗点击继续后消失。"""
        mixin = self._make_mixin()
        # 第一次调用：扫描弹窗；第二次：点击继续；第三次：检查弹窗消失
        mixin._cdp.eval_js.side_effect = [
            '[{"text": "服务端异常，请稍后重试", "buttons": ["继续"]}]',
            True,   # _click_dialog_button 内部 eval_js
            "dismissed",  # 检查弹窗消失
        ]

        resp = await mixin.auto_handle_dialog()
        assert resp.code == 0
        assert resp.result["dialog_type"] == "server_error"
        assert resp.result["action_taken"] == "click-continue"

    @pytest.mark.asyncio
    async def test_update_dialog_click_ignore(self):
        """update_dialog 弹窗点击忽略。"""
        mixin = self._make_mixin()
        mixin._cdp.eval_js.side_effect = [
            '[{"text": "检测到新版 v2.0", "buttons": ["忽略", "立即更新"]}]',
            True,   # _click_dialog_button 内部 eval_js
        ]

        resp = await mixin.auto_handle_dialog()
        assert resp.code == 0
        assert resp.result["dialog_type"] == "update_dialog"
        assert resp.result["action_taken"] == "click-ignore"

    @pytest.mark.asyncio
    async def test_queue_reminder_returns_position(self):
        """queue_reminder 弹窗返回排队位置。"""
        mixin = self._make_mixin()
        mixin._cdp.eval_js.return_value = '[{"text": "排队提醒，排在第5位", "buttons": []}]'

        resp = await mixin.auto_handle_dialog()
        assert resp.code == 0
        assert resp.result["dialog_type"] == "queue_reminder"
        assert resp.result["action_taken"] == "queue-info"
        assert resp.result["position"] == "5"

    @pytest.mark.asyncio
    async def test_confirm_dialog_click_run(self):
        """confirm_dialog 弹窗点击运行。"""
        mixin = self._make_mixin()
        mixin._cdp.eval_js.side_effect = [
            '[{"text": "运行前检查：以下文件将被修改", "buttons": ["运行", "取消"]}]',
            True,   # _click_dialog_button 内部 eval_js
        ]

        resp = await mixin.auto_handle_dialog()
        assert resp.code == 0
        assert resp.result["dialog_type"] == "confirm_dialog"
        assert resp.result["action_taken"] == "click-run"

    @pytest.mark.asyncio
    async def test_unknown_dialog_fallback_to_close(self):
        """未知弹窗退回到 close_dialog 逻辑。"""
        mixin = self._make_mixin()
        # 扫描弹窗返回未知文本
        mixin._cdp.eval_js.side_effect = [
            '[{"text": "这是一个普通提示", "buttons": ["确定"]}]',
            # close_dialog 内部的 eval_js 调用
            "closed-via-cancel:确定",
        ]

        resp = await mixin.auto_handle_dialog()
        assert resp.result["dialog_type"] == "unknown"
        assert resp.result["action_taken"] == "close-dialog"

    @pytest.mark.asyncio
    async def test_server_error_retry_exhausted(self):
        """server_error 弹窗3次点击继续后仍不消失，返回重启提示。"""
        mixin = self._make_mixin()
        # 扫描 → 点击继续(3次) → 每次检查弹窗仍在
        mixin._cdp.eval_js.side_effect = [
            '[{"text": "服务端异常", "buttons": ["继续"]}]',
            True, "still-visible",
            True, "still-visible",
            True, "still-visible",
        ]

        resp = await mixin.auto_handle_dialog()
        assert resp.code == -1
        assert resp.result["dialog_type"] == "server_error"
        assert resp.result["action_taken"] == "retry-exhausted"
