#!/usr/bin/env python3
"""集成测试：连接真实的 Trae CN SOLO 实例进行端到端验收。

运行方式：
  python -m pytest tests/test_integration.py -v          # 需要 Trae CN 在运行
  python -m pytest tests/ -v -m "not integration"         # 跳过集成测试

环境变量：
  TRAECTL_CDP_HOST / CDP_HOST  — CDP 主机 (默认 127.0.0.1)
  TRAECTL_CDP_PORT / CDP_PORT  — CDP 端口 (默认 9224)
"""

import json
import os
import subprocess
import urllib.request

import pytest

from traectl.cdp_client import CDPClient

# ── 配置 ───────────────────────────────────────────────
CDP_HOST = os.environ.get("TRAECTL_CDP_HOST", os.environ.get("CDP_HOST", "127.0.0.1"))
CDP_PORT = int(os.environ.get("TRAECTL_CDP_PORT", os.environ.get("CDP_PORT", "9224")))
PING_TIMEOUT = 5


# ── 自动跳过 ──────────────────────────────────────────
def _is_trae_cn_reachable() -> bool:
    """检测 Trae CN CDP 端口是否可达。"""
    try:
        url = f"http://{CDP_HOST}:{CDP_PORT}/json/version"
        resp = urllib.request.urlopen(url, timeout=PING_TIMEOUT)
        return resp.status == 200
    except Exception:
        return False


def pytest_collection_modifyitems(items):
    if _is_trae_cn_reachable():
        return
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(pytest.mark.skip(reason=f"Trae CN 不可达 ({CDP_HOST}:{CDP_PORT})"))


# ── 工具函数 ──────────────────────────────────────────
def _traectl(*args: str, timeout: int = 30) -> dict:
    """运行 traectl 命令并返回解析后的 JSON。
    
    自动识别需要 --port 参数的命令（doctor 等诊断命令不需要）。
    """
    port_cmds = {"doctor", "version", "exit-codes", "commands", "help", "schema", "categories"}
    if args and args[0] not in port_cmds:
        cmd = ["python3", "-m", "traectl", *args, "--port", str(CDP_PORT)]
    else:
        cmd = ["python3", "-m", "traectl", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    assert result.returncode == 0, f"命令 {' '.join(cmd)} 失败:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    return json.loads(result.stdout)


# ══════════════════════════════════════════════════════════
# CDP 连接测试
# ══════════════════════════════════════════════════════════

class TestCDPConnection:
    """通过 CDPClient 直接连接真实 Trae CN。"""

    @pytest.mark.integration
    def test_connect_and_eval_js(self):
        """能连上 Trae CN 并执行简单 JS。"""
        async def run():
            client = CDPClient(CDP_HOST, CDP_PORT)
            await client.connect()
            result = await client.eval_js("1 + 1")
            await client.disconnect()
            assert result == "2" or result == 2, f"JS eval 返回异常: {result}"
        import asyncio
        asyncio.run(run())

    @pytest.mark.integration
    def test_capture_screenshot(self):
        """能从 CDP 截图返回 base64 数据。"""
        async def run():
            client = CDPClient(CDP_HOST, CDP_PORT)
            await client.connect()
            data = await client.capture_screenshot()
            await client.disconnect()
            assert data, "截图数据为空"
            assert len(data) > 100, f"截图数据过短 ({len(data)} bytes)"
            assert isinstance(data, str), "截图数据不是 base64 字符串"
        import asyncio
        asyncio.run(run())


# ══════════════════════════════════════════════════════════
# CLI 命令测试
# ══════════════════════════════════════════════════════════

class TestTraectlCLI:
    """通过子进程调用真实 traectl 命令。"""

    @pytest.mark.integration
    def test_doctor(self):
        """traectl doctor 返回完整诊断信息。"""
        data = _traectl("doctor", timeout=15)
        assert data["ok"] is True
        assert data["type"] == "doctor.info"
        required = ("system", "release", "machine", "python_version", "temp_dir", "config_dir", "cdp_port")
        for key in required:
            assert key in data["data"], f"缺少字段: {key}"

    @pytest.mark.integration
    def test_status(self):
        """traectl status 返回 SOLO 状态。"""
        data = _traectl("status", timeout=15)
        assert data["ok"] is True
        assert data["type"] == "status.get"
        for key in ("inputText", "sendDisabled", "taskCount", "currentModel", "isThinking"):
            assert key in data["data"], f"缺少字段: {key}"

    @pytest.mark.integration
    def test_chat(self):
        """traectl chat 能读取聊天内容。"""
        data = _traectl("chat", timeout=15)
        assert data["ok"] is True
        assert data["type"] == "chat.read"
        assert "content" in data["data"]

    @pytest.mark.integration
    def test_screenshot(self):
        """traectl screenshot 能截图返回。"""
        data = _traectl("screenshot", timeout=15)
        assert data["ok"] is True
        assert "base64_length" in data["data"]
        assert data["data"]["base64_length"] > 100


    def test_doctor_paths_match_platform(self):
        """doctor 输出的路径和系统类型匹配。"""
        import platform as sys_platform
        data = _traectl("doctor", timeout=15)
        info = data["data"]
        actual_os = sys_platform.system()
        assert info["system"] == actual_os, f"系统不匹配: {info['system']} != {actual_os}"
        if actual_os == "Linux":
            assert info["temp_dir"] == "/tmp"
        elif actual_os == "Windows":
            assert "TEMP" in info["temp_dir"].upper() or "Temp" in info["temp_dir"]
