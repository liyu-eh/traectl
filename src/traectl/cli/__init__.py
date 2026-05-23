#!/usr/bin/env python3
"""traectl CLI 入口 — 将所有子模块的命令注册到 app 上。"""

from ._core import *  # noqa: F401,F403
from ._submit import *  # noqa: F401,F403
from ._query import *  # noqa: F401,F403
from ._interact import *  # noqa: F401,F403
from ._agent import *  # noqa: F401,F403
from ._workspace import *  # noqa: F401,F403
from ._introspect import *  # noqa: F401,F403
