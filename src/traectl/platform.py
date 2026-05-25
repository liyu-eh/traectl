#!/usr/bin/env python3
"""平台检测模块 — 提供跨平台（Windows / Linux / macOS）路径与系统信息。"""

import os
import platform
import sys
from pathlib import Path


def is_windows() -> bool:
    """当前操作系统是否为 Windows。"""
    return platform.system() == "Windows"


def is_linux() -> bool:
    """当前操作系统是否为 Linux。"""
    return platform.system() == "Linux"


def is_macos() -> bool:
    """当前操作系统是否为 macOS。"""
    return platform.system() == "Darwin"


def get_temp_dir() -> Path:
    """返回平台兼容的临时目录。

    - Windows: ``%TEMP%``（通常为 ``C:\\Users\\<user>\\AppData\\Local\\Temp``）
    - Linux/macOS: ``/tmp`` 或 ``$TMPDIR``
    """
    return Path(os.environ.get("TEMP") if is_windows() else os.environ.get("TMPDIR", "/tmp"))


def get_config_dir() -> Path:
    """返回 traectl 配置目录。

    - Windows: ``%APPDATA%\\traectl``
    - Linux/macOS: ``~/.config/traectl``（遵循 XDG）
    """
    if is_windows():
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / "traectl"
        # 降级到用户主目录
        return Path.home() / "AppData" / "Roaming" / "traectl"
    # Linux / macOS
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "traectl"
    return Path.home() / ".config" / "traectl"


def get_screenshot_path(filename: str = None) -> Path:
    """返回平台兼容的截图保存路径。

    若未提供文件名，则自动生成带时间戳的文件名。
    """
    from datetime import datetime

    temp_dir = get_temp_dir()
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"trae_screenshot_{timestamp}.png"
    return temp_dir / filename


def get_platform_info() -> dict:
    """返回诊断信息字典，用于 ``traectl doctor``。"""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": sys.version,
        "python_executable": sys.executable,
        "temp_dir": str(get_temp_dir()),
        "config_dir": str(get_config_dir()),
        "cdp_host": os.environ.get("TRAECTL_CDP_HOST", os.environ.get("CDP_HOST", "127.0.0.1")),
        "cdp_port": int(os.environ.get("TRAECTL_CDP_PORT", os.environ.get("CDP_PORT", "9222"))),
    }
