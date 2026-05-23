#!/usr/bin/env python3
"""Trae CN SOLO 控制器：基于 CDP 的 SOLO 面板操作封装。"""

import os
from typing import TYPE_CHECKING

from .cdp_client import CDPClient
from .mixins.chat_mixin import ChatMixin
from .mixins.model_mixin import ModelMixin
from .mixins.task_mixin import TaskMixin
from .mixins.editor_mixin import EditorMixin
from .mixins.terminal_mixin import TerminalMixin
from .mixins.git_mixin import GitMixin
from .mixins.health_mixin import HealthMixin
from .mixins.media_mixin import MediaMixin

if TYPE_CHECKING:
    from .mixins.base import TraeSoloProtocol


class TraeSoloController(
    ChatMixin,
    ModelMixin,
    TaskMixin,
    EditorMixin,
    TerminalMixin,
    GitMixin,
    HealthMixin,
    MediaMixin,
):
    """Trae CN SOLO 编码代理控制器。满足 TraeSoloProtocol 类型协议。"""

    def __init__(self, cdp: CDPClient, workspace_root: str = ""):
        self._cdp = cdp
        self._workspace_root = workspace_root or os.getcwd()
        self._git_cmd = None  # lazy detect git on first use
