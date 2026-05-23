#!/usr/bin/env python3
"""配置模块：集中化配置数据类和环境变量。

符合 agentic-cli-design 规范：
- 所有退出码分类（0/2/3/4）
- 标准标志名称统一
- 配置支持 env override
- 环境变量统一使用 TRAECTL_* 前缀（向后兼容旧前缀）
"""

import os
import json as _json
from dataclasses import dataclass
from pathlib import Path


def _env_with_fallback(new_key: str, old_key: str, default: str) -> str:
    val = os.environ.get(new_key)
    if val is not None:
        return val
    return os.environ.get(old_key, default)


# ── CDP 连接配置 ──────────────────────────────────────────────
CDP_PORT = int(_env_with_fallback("TRAECTL_CDP_PORT", "CDP_PORT", "9222"))
CDP_HOST = _env_with_fallback("TRAECTL_CDP_HOST", "CDP_HOST", "127.0.0.1")
SOLO_TIMEOUT = int(_env_with_fallback("TRAECTL_TIMEOUT", "SOLO_TIMEOUT", "300"))
STABLE_THRESHOLD = int(_env_with_fallback("TRAECTL_STABLE_THRESHOLD", "SOLO_STABLE_THRESHOLD", "3"))
POLL_INTERVAL = int(_env_with_fallback("TRAECTL_POLL_INTERVAL", "SOLO_POLL_INTERVAL", "2"))
MAX_RETRY_INTERVAL = int(_env_with_fallback("TRAECTL_CDP_MAX_RETRY_INTERVAL", "CDP_MAX_RETRY_INTERVAL", "30"))
INITIAL_RETRY_INTERVAL = int(_env_with_fallback("TRAECTL_CDP_INITIAL_RETRY_INTERVAL", "CDP_INITIAL_RETRY_INTERVAL", "1"))
MAX_RETRIES = int(_env_with_fallback("TRAECTL_CDP_MAX_RETRIES", "CDP_MAX_RETRIES", "5"))

# ── XDG 配置目录 ──────────────────────────────────────────────
CONFIG_DIR = Path(os.environ.get("TRAECTL_CONFIG_DIR", os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")))
CONFIG_FILE = CONFIG_DIR / "traectl" / "config.json"

# ── Schema 版本 ───────────────────────────────────────────────
SCHEMA_VERSION = 1

# ── 退出码（符合 agentic-cli-design 标准） ───────────────────
EXIT_SUCCESS = 0          # 成功
EXIT_GENERAL = 1          # 一般错误
EXIT_USAGE = 2            # 参数/用法错误
EXIT_AUTH = 3             # 认证/权限错误
EXIT_RETRYABLE = 4        # 可重试（限流/网络超时）
EXIT_CONFIRMATION_REQUIRED = 10  # 需要确认（高风险操作）


@dataclass
class Config:
    """集中化的配置数据类。"""
    cdp_host: str = CDP_HOST
    cdp_port: int = CDP_PORT
    solo_timeout: int = SOLO_TIMEOUT
    stable_threshold: int = STABLE_THRESHOLD
    poll_interval: int = POLL_INTERVAL
    max_retry_interval: int = MAX_RETRY_INTERVAL
    initial_retry_interval: int = INITIAL_RETRY_INTERVAL
    max_retries: int = MAX_RETRIES


# Agent 角色模板
AGENT_ROLES = {
    "architect": {
        "name": "架构师",
        "description": "系统架构设计、技术选型、项目结构规划、接口设计",
        "prompt_prefix": "你是一个资深架构师。请从系统设计角度分析需求，给出架构方案、技术选型建议、模块划分和接口定义。",
        "recommended_models": ["DeepSeek-V4-Pro", "Kimi-K2.6", "Qwen3.6-Plus"],
    },
    "frontend": {
        "name": "前端工程师",
        "description": "UI/UX 实现、前端组件开发、样式、交互逻辑",
        "prompt_prefix": "你是一个前端工程师。请专注于 UI 组件实现、样式美化、交互逻辑和前端架构。确保代码可维护、响应式设计。",
        "recommended_models": ["DeepSeek-V4-Pro", "Kimi-K2.6", "GLM-5.1Beta"],
    },
    "backend": {
        "name": "后端工程师",
        "description": "API 开发、数据库设计、业务逻辑、服务端架构",
        "prompt_prefix": "你是一个后端工程师。请专注于 API 设计、数据库操作、业务逻辑实现和服务端架构。确保代码安全、高效、可扩展。",
        "recommended_models": ["DeepSeek-V4-Pro", "Kimi-K2.6", "Qwen3.6-Plus"],
    },
    "tester": {
        "name": "测试工程师",
        "description": "编写测试、质量保证、Bug 复现和验证",
        "prompt_prefix": "你是一个测试工程师。请专注于编写全面的测试用例、边界条件测试、集成测试。确保覆盖率和代码质量。",
        "recommended_models": ["DeepSeek-V4-FlashBeta", "Doubao-Seed-2.0-CodeBeta", "MiniMax-M2.5"],
    },
    "reviewer": {
        "name": "代码审查员",
        "description": "代码审查、安全审计、性能优化建议",
        "prompt_prefix": "你是一个严格的代码审查员。请审查代码的安全性、性能、可维护性和最佳实践。指出所有问题并给出改进建议。",
        "recommended_models": ["DeepSeek-V4-Pro", "Kimi-K2.6", "Qwen3.6-Plus"],
    },
    "debugger": {
        "name": "调试专家",
        "description": "Bug 定位、问题排查、错误修复",
        "prompt_prefix": "你是一个调试专家。请仔细分析错误信息、堆栈跟踪和相关代码，精确定位 Bug 根因并给出修复方案。",
        "recommended_models": ["DeepSeek-V4-Pro", "Kimi-K2.6", "Doubao-Seed-2.0-CodeBeta"],
    },
}

# 任务类型 → 角色的映射
TASK_TYPE_ROLE_MAP = {
    "architecture": "architect", "架构": "architect", "设计": "architect",
    "技术选型": "architect", "接口设计": "architect", "模块划分": "architect",
    "系统设计": "architect", "项目结构": "architect", "design": "architect",
    "frontend": "frontend", "前端": "frontend", "ui": "frontend",
    "页面": "frontend", "组件": "frontend", "样式": "frontend",
    "界面": "frontend", "交互": "frontend", "component": "frontend",
    "page": "frontend", "widget": "frontend", "css": "frontend",
    "html": "frontend", "flutter": "frontend", "dart": "frontend",
    "backend": "backend", "后端": "backend", "api": "backend",
    "database": "backend", "数据库": "backend", "server": "backend",
    "服务端": "backend", "接口实现": "backend", "业务逻辑": "backend",
    "test": "tester", "testing": "tester", "测试": "tester",
    "unit test": "tester", "e2e": "tester", "integration test": "tester",
    "review": "reviewer", "audit": "reviewer", "审查": "reviewer",
    "refactor": "reviewer", "重构": "reviewer", "安全审计": "reviewer",
    "性能优化": "reviewer", "代码质量": "reviewer",
    "debug": "debugger", "fix": "debugger", "bug": "debugger",
    "error": "debugger", "修复": "debugger", "调试": "debugger",
    "排查": "debugger", "崩溃": "debugger", "crash": "debugger",
    "异常": "debugger",
}

# ── 配置持久化 ──────────────────────────────────────────────

DEFAULT_CONFIG = {
    "cdp_host": CDP_HOST,
    "cdp_port": CDP_PORT,
    "solo_timeout": SOLO_TIMEOUT,
    "stable_threshold": STABLE_THRESHOLD,
    "poll_interval": POLL_INTERVAL,
}


def _ensure_config_dir():
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)


def load_config() -> dict:
    """从磁盘加载配置，合并默认值。"""
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = _json.load(f)
        except (_json.JSONDecodeError, IOError):
            saved = {}
        merged = {**DEFAULT_CONFIG, **saved}
        return merged
    return dict(DEFAULT_CONFIG)


def save_config(config: dict) -> None:
    """将配置持久化到磁盘。"""
    _ensure_config_dir()
    with open(CONFIG_FILE, "w") as f:
        _json.dump(config, f, indent=2, ensure_ascii=False)


def get_config_value(key: str) -> str:
    """读取单个配置项。先查磁盘，再查默认值。"""
    config = load_config()
    if key in config:
        return str(config[key])
    return ""


def set_config_value(key: str, value: str) -> dict:
    """设置单个配置项并持久化。返回更新后的完整配置。"""
    config = load_config()
    int_keys = {"cdp_port", "solo_timeout", "stable_threshold", "poll_interval"}
    if key in int_keys:
        config[key] = int(value)
    else:
        config[key] = value
    save_config(config)
    return config


# 常量定义
CONSTANTS = {
    "PROGRESS_KEYWORDS": [
        "正在分析问题", "正在思考", "正在处理", "正在生成",
        "正在执行", "正在搜索", "正在编写",
        "analyzing", "thinking", "generating",
        "processing", "executing", "searching", "writing",
    ],
    "QUEUE_KEYWORDS": [
        "排队提醒", "排在第", "排队中", "当前模型请求", "请稍候",
    ],
    "STATUS_INDICATORS": [
        "SOLO Agent", "已完成", "0/", "任务", "任务完成",
    ],
    "FOLDER_PROMPT_MARKERS": [
        "请先打开文件夹", "打开文件夹", "新建项目",
    ],
    "QUEUE_INFO_FALLBACK": "排队中",
    "NO_CHAT_CONTENT": "no chat content",
    "NO_CHAT_CONTAINER": "no chat container",
    "TIMEOUT_MSG_TEMPLATE": "等待超时 ({timeout}s)。\n{progress}最后内容:\n\n{content}{salvage}{snapshot}",
    "TIMEOUT_EMPTY_RETRY_MSG": "超时且内容为空，重试 {retry}/{max_retries}",
    "TIMEOUT_FINAL_MSG": "等待超时 ({timeout}s)，重试 {max_retries} 次后仍无有效内容。",
    "DIALOG_PATTERNS": {
        "server_error": ["服务端异常", "请稍后重试", "系统未知错误"],
        "error_2000000": ["2000000", "系统未知错误"],
        "update_dialog": ["检测到新版"],
        "queue_reminder": ["排队提醒", "排在第"],
        "confirm_dialog": ["运行前检查", "确认执行", "确定要"],
    },
}

# DOM 选择器
SELECTORS = {
    "new_task_btn": '[class*="new-task-button"]',
    "input_box": ".chat-input-v2-input-box-editable",
    "send_btn": ".chat-input-v2-send-button",
    "chat_container": ".chat-list-wrapper",
    "task_list": '[class*="task-items-list"]',
    "task_item": '[class*="task-item"]',
    "inline_delete": '[class*="delete-files-command-card"] [class*="delete"]',
    "open_folder": ".icd-open-folder-card",
    "model_trigger": ".icd-model-select-trigger",
    "model_trigger_value": ".icd-model-select-trigger-value",
    "model_portal": ".icube-model-select-portal",
    "model_item": ".icube-model-select-portal-model-item",
    "model_item_name": ".icube-model-select-portal-model-item-wrapper",
    "auto_mode_switch": ".icd-mode-select-mode-item-switch input[type=checkbox]",
    "thinking_indicator": '[class*="thinking"], [class*="generating"]',
    "delete_task_icon": '[class*="delete-task"], [class*="trash"]',
    "dialog_overlay": '[class*="overlay"], [class*="modal"], [class*="mask"], [class*="backdrop"]',
    "user_msg_content": ".icube-value .value, .value",
    "assistant_msg_content": ".assistant-chat-turn-content",
    "chat_turn_heading": ".chat-turn-heading",
}
