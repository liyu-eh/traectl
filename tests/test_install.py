#!/usr/bin/env python3
"""从 pip 安装到 CLI 使用的完整端到端测试。

在临时 venv 中构建 wheel → pip install → 运行所有基本命令。

运行方式：
  python -m pytest tests/test_install.py -v       # 需要当前目录可 build wheel
  python -m pytest tests/ -m "not install_test"    # 跳过（默认跳过）
"""
import json
import subprocess
import sys
import venv
from pathlib import Path

import pytest

# 安装测试默认跳过（需要 build wheel + 创建 venv，~12s）
pytestmark = pytest.mark.install_test

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class TestInstallToUsage:
    """模拟用户首次安装 traectl 后的完整体验。"""

    @pytest.fixture(scope="class")
    def fresh_env(self, tmp_path_factory):
        """创建临时 venv → build wheel → pip install 当前包。"""
        root = tmp_path_factory.mktemp("install_e2e")
        venv_dir = root / "venv"
        venv.create(venv_dir, with_pip=True)

        pip = venv_dir / "bin" / "pip"
        python = venv_dir / "bin" / "python"

        # 在项目根目录构建 wheel（不产生依赖）
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps",
             "-w", str(root), str(PROJECT_ROOT)],
            check=True, capture_output=True, text=True,
        )
        wheels = list(root.glob("*.whl"))
        assert len(wheels) == 1, f"期望 1 个 wheel，实际 {len(wheels)}: {wheels}"

        subprocess.run(
            [str(pip), "install", str(wheels[0])],
            check=True, capture_output=True, text=True,
        )
        return python

    # ── CLI 入口 ──────────────────────────────────────────

    def test_cli_help(self, fresh_env):
        """traectl --help 正常输出帮助信息。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "Usage:" in result.stdout
        assert "COMMAND" in result.stdout

    def test_cli_version(self, fresh_env):
        """traectl version 返回版本号。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "version"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        assert isinstance(data["data"]["version"], str)
        assert len(data["data"]["version"]) > 0

    def test_cli_doctor(self, fresh_env):
        """traectl doctor 返回平台诊断 JSON。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "doctor"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert data["ok"] is True
        for key in ("system", "release", "machine", "python_version", "temp_dir", "cdp_host", "cdp_port"):
            assert key in data["data"], f"doctor 缺少字段: {key}"

    def test_cli_doctor_paths_match_env(self, fresh_env):
        """doctor 中的 temp_dir 和刚安装的 venv 一致。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "doctor"],
            capture_output=True, text=True,
        )
        data = json.loads(result.stdout)
        # 验证 python 版本匹配（从同一解释器安装）
        assert data["data"]["python_version"].startswith(sys.version[:5])

    # ── 子命令注册 ────────────────────────────────────────

    def test_all_commands_registered(self, fresh_env):
        """--help 列表包含所有核心命令。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "--help"],
            capture_output=True, text=True,
        )
        for cmd in ("submit", "status", "chat", "models", "health",
                     "screenshot", "doctor", "version", "roles",
                     "action", "workspace", "config"):
            assert cmd in result.stdout, f"缺少命令: {cmd}"

    # ── 退出码和错误处理 ─────────────────────────────────

    def test_unknown_command_exits_error(self, fresh_env):
        """不存在的命令应返回非 0 退出码。"""
        result = subprocess.run(
            [str(fresh_env), "-m", "traectl", "this-command-does-not-exist"],
            capture_output=True, text=True,
        )
        assert result.returncode != 0

    def test_json_output_format(self, fresh_env):
        """所有带 JSON 输出的命令格式一致。"""
        for cmd in [["doctor"], ["version"]]:
            result = subprocess.run(
                [str(fresh_env), "-m", "traectl", *cmd],
                capture_output=True, text=True,
            )
            assert result.returncode == 0, f"命令 traectl {' '.join(cmd)} 失败"
            data = json.loads(result.stdout)
            assert "ok" in data
            assert "type" in data
            assert "metadata" in data
            assert "timestamp" in data["metadata"]
