"""JS 模板模块：所有 CDP 注入的 JavaScript 代码集中管理。

每个函数返回一段 JS 字符串，供 eval_js() 执行。
参数通过函数入参传入，不依赖 Python 运行时变量。
"""

from ._chat_mixin import *
from ._task_mixin import *
from ._media_mixin import *
from ._terminal_mixin import *
from ._editor_mixin import *
from ._model_mixin import *
