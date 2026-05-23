import re
import ast
from pathlib import Path

from traectl.config import SELECTORS, CONSTANTS, AGENT_ROLES
from traectl.cdp_client import ConnectionState


SRC_DIR = Path(__file__).parent.parent / "src" / "traectl"
CONTROLLER_PATH = SRC_DIR / "controller.py"
CDP_CLIENT_PATH = SRC_DIR / "cdp_client.py"
MIXINS_DIR = SRC_DIR / "mixins"
JS_TEMPLATES_PATH = SRC_DIR / "js_templates.py"
JS_TEMPLATES_DIR = SRC_DIR / "js_templates"
RESPONSE_WAITER_PATH = SRC_DIR / "response_waiter.py"

REQUIRED_SELECTOR_KEYS = [
    "new_task_btn", "input_box", "send_btn", "chat_container",
    "task_list", "task_item", "inline_delete", "open_folder",
    "model_trigger", "model_trigger_value", "model_item", "model_item_name",
    "auto_mode_switch", "thinking_indicator", "delete_task_icon",
    "dialog_overlay", "user_msg_content", "assistant_msg_content",
    "chat_turn_heading",
]


def _extract_used_selector_keys(file_path: Path) -> set[str]:
    content = file_path.read_text(encoding="utf-8")
    # 匹配 SELECTORS["key"] 和 selectors["key"]（js_templates.py 使用小写参数名）
    matches = re.findall(r'(?:SELECTORS|selectors)\["(\w+)"\]', content)
    return set(matches)


def _extract_used_selector_keys_from_dir(dir_path: Path) -> set[str]:
    """从目录下所有 .py 文件中提取 SELECTORS 使用。"""
    keys = set()
    if dir_path.is_dir():
        for f in dir_path.glob("*.py"):
            keys |= _extract_used_selector_keys(f)
    return keys


def test_selectors_keys_present():
    for key in REQUIRED_SELECTOR_KEYS:
        assert key in SELECTORS, f"SELECTORS missing key: {key}"
        assert SELECTORS[key], f"SELECTORS key {key} has empty value"


def test_selectors_keys_match_usage():
    used_keys = _extract_used_selector_keys(CONTROLLER_PATH)
    used_keys |= _extract_used_selector_keys(CDP_CLIENT_PATH)
    used_keys |= _extract_used_selector_keys_from_dir(MIXINS_DIR)
    used_keys |= _extract_used_selector_keys_from_dir(JS_TEMPLATES_DIR)
    used_keys |= _extract_used_selector_keys(JS_TEMPLATES_PATH)

    for key in used_keys:
        assert key in SELECTORS, f"SELECTORS key used but not defined: {key}"

    config_keys = set(SELECTORS.keys())
    unused = config_keys - used_keys
    assert len(unused) <= 3, (
        f"Too many unused SELECTORS keys: {unused}. "
        f"Remove or use them in code."
    )


def test_connection_state_defaults():
    assert ConnectionState.DISCONNECTED == "disconnected"
    assert ConnectionState.CONNECTING == "connecting"
    assert ConnectionState.CONNECTED == "connected"


def test_agent_roles_structure():
    for role_key, role_data in AGENT_ROLES.items():
        assert "name" in role_data, f"Agent role {role_key} missing 'name'"
        assert "description" in role_data, f"Agent role {role_key} missing 'description'"
        assert "prompt_prefix" in role_data, f"Agent role {role_key} missing 'prompt_prefix'"
        assert "recommended_models" in role_data, f"Agent role {role_key} missing 'recommended_models'"
        assert isinstance(role_data["recommended_models"], list)
        assert len(role_data["recommended_models"]) > 0


def test_constants_keys_present():
    assert "PROGRESS_KEYWORDS" in CONSTANTS
    assert "QUEUE_KEYWORDS" in CONSTANTS
    assert "STATUS_INDICATORS" in CONSTANTS
    assert "FOLDER_PROMPT_MARKERS" in CONSTANTS
    assert "QUEUE_INFO_FALLBACK" in CONSTANTS
    assert "NO_CHAT_CONTENT" in CONSTANTS
    assert "NO_CHAT_CONTAINER" in CONSTANTS
    assert "TIMEOUT_MSG_TEMPLATE" in CONSTANTS
    assert "TIMEOUT_EMPTY_RETRY_MSG" in CONSTANTS
    assert "TIMEOUT_FINAL_MSG" in CONSTANTS


def test_constants_used_in_controller():
    """验证 controller、mixin 及 js_templates 引用了 CONSTANTS（仅检查实际使用的 key）。"""
    sources = [CONTROLLER_PATH.read_text(encoding="utf-8")]
    if MIXINS_DIR.is_dir():
        for f in MIXINS_DIR.glob("*.py"):
            sources.append(f.read_text(encoding="utf-8"))
    if JS_TEMPLATES_DIR.is_dir():
        for f in JS_TEMPLATES_DIR.glob("*.py"):
            sources.append(f.read_text(encoding="utf-8"))
    sources.append(JS_TEMPLATES_PATH.read_text(encoding="utf-8"))
    sources.append(RESPONSE_WAITER_PATH.read_text(encoding="utf-8"))
    combined = "\n".join(sources)
    assert "CONSTANTS" in combined, "controller/mixins should import CONSTANTS"
    # 实际使用的常量
    used_keys = [
        "QUEUE_INFO_FALLBACK",
        "NO_CHAT_CONTAINER",
        "NO_CHAT_CONTENT",
        "TIMEOUT_FINAL_MSG",
    ]
    for key in used_keys:
        # 匹配 CONSTANTS["key"] 和 constants["key"]（js_templates.py 使用小写参数名）
        pattern = re.compile(r'(?:CONSTANTS|constants)\["' + re.escape(key) + r'"\]')
        assert pattern.search(combined), (
            f"CONSTANTS[{key!r}] should be referenced in controller/mixins/js_templates"
        )
