#!/usr/bin/env python3
"""TraeSoloProtocol — 定义所有 Mixin 必须提供的接口方法（类型检查协议）。"""

from typing import Protocol

from ..response import StandardResponse


class TraeSoloProtocol(Protocol):
    """定义所有 Mixin 必须提供的接口方法。确保跨 Mixin 调用有类型检查。

    Protocol 只用于静态类型检查，不会在运行时强制要求实现。
    TraeSoloController 组合所有 Mixin 后会拥有全部方法实现。
    """

    # 来自 ChatMixin
    async def start_new_task(self) -> StandardResponse: ...

    async def type_message(self, text: str) -> StandardResponse: ...

    async def send_message(self) -> StandardResponse: ...

    async def auto_confirm(self) -> StandardResponse: ...

    async def get_chat_content(self, max_length: int = 5000) -> StandardResponse: ...

    # 来自 ModelMixin
    async def switch_model(self, model_name: str) -> StandardResponse: ...

    # 来自 MediaMixin
    async def close_dialog(self) -> StandardResponse: ...
