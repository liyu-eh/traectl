import json
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from traectl.cli import (
    _display,
    _exit,
    _ndjson_line,
    _print_json,
    _RAW_OUTPUT,
    _OUTPUT_FORMAT,
    app,
)
from traectl.response import ok as mk_ok, error as mk_error, JsonResponse


class TestDisplayOutput:
    """测试 _display 输出格式选择（json/ndjson/text）"""

    def test_display_json_default(self, capsys):
        """默认模式下 _display 输出 JSON 字符串到 stdout。"""
        text = mk_ok({"status": "ok"}, type_="test")
        _display(text)
        captured = capsys.readouterr()
        assert captured.out.strip() != ""
        parsed = json.loads(captured.out.strip())
        assert parsed["ok"] is True
        assert parsed["data"] == {"status": "ok"}

    def test_display_ndjson_mode(self, capsys):
        """ndjson 模式下 _display 输出单行 JSON。"""
        from unittest.mock import patch
        with patch("traectl.cli._core._OUTPUT_FORMAT", "ndjson"):
            text = mk_ok({"item": 1}, type_="test")
            _display(text)
            captured = capsys.readouterr()
            lines = captured.out.strip().split("\n")
            assert len(lines) == 1
            parsed = json.loads(lines[0])
            assert parsed["ok"] is True

    def test_display_raw_text_fallback(self, capsys):
        """非 JSON 文本 fallback 直接输出。"""
        from unittest.mock import patch
        with patch("traectl.cli._core._OUTPUT_FORMAT", "json"):
            _display("plain text message")
            captured = capsys.readouterr()
            assert "plain text message" in captured.out

    def test_ndjson_with_invalid_json(self, capsys):
        """ndjson 模式下传入非 JSON 文本直接输出。"""
        from unittest.mock import patch
        with patch("traectl.cli._core._OUTPUT_FORMAT", "ndjson"):
            _display("not json at all")
            captured = capsys.readouterr()
            assert captured.out.strip() == "not json at all"


class TestPrintJson:
    """测试 _print_json 辅助函数"""

    def test_print_json_with_dict(self, capsys):
        data = {"key": "value"}
        _print_json(data)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed == data

    def test_print_json_with_string(self, capsys):
        _print_json("hello")
        captured = capsys.readouterr()
        assert captured.out.strip() == "hello"


class TestNdjsonLine:
    """测试 _ndjson_line 单行输出"""

    def test_ndjson_line_outputs_dict(self, capsys):
        obj = {"type": "progress", "elapsed": 5}
        _ndjson_line(obj)
        captured = capsys.readouterr()
        parsed = json.loads(captured.out.strip())
        assert parsed == obj


class TestExit:
    """测试 _exit 函数"""

    def test_exit_raises_typer_exit(self):
        import typer
        with pytest.raises(typer.Exit) as exc_info:
            _exit(2)
        assert exc_info.value.exit_code == 2


def _get_command_name(cmd):
    """Typer 命令名：优先 name 属性，否则从 callback.__name__ 推断。"""
    if cmd.name is not None:
        return cmd.name
    if cmd.callback is not None:
        return cmd.callback.__name__
    return None


class TestTyperCommandsImport:
    """测试命令可通过 typer 导入"""

    def test_app_has_registered_commands(self):
        assert len(app.registered_commands) > 0
        command_names = [_get_command_name(cmd) for cmd in app.registered_commands]
        assert "submit" in command_names
        assert "status" in command_names
        assert "models" in command_names
        assert "chat" in command_names
        assert "health" in command_names

    def test_app_has_registered_groups(self):
        group_names = [g.name for g in app.registered_groups]
        assert "workspace" in group_names
        assert "config" in group_names

    def test_version_command_exists(self):
        command_names = [_get_command_name(cmd) for cmd in app.registered_commands]
        assert "version" in command_names

    def test_roles_command_exists(self):
        command_names = [_get_command_name(cmd) for cmd in app.registered_commands]
        assert "roles" in command_names

    def test_action_command_exists(self):
        command_names = [_get_command_name(cmd) for cmd in app.registered_commands]
        assert "action" in command_names


class TestResponseHelpers:
    """测试 response 辅助函数与 CLI 集成"""

    def test_mk_ok_returns_valid_json(self):
        result = mk_ok({"data": 42}, type_="test.ok")
        parsed = json.loads(result)
        assert parsed["ok"] is True
        assert parsed["data"] == {"data": 42}
        assert parsed["type"] == "test.ok"
        assert "timestamp" in parsed["metadata"]

    def test_mk_error_returns_valid_json(self):
        result = mk_error("test_error", "something failed", exit_code=2)
        parsed = json.loads(result)
        assert parsed["ok"] is False
        assert parsed["error"]["code"] == "test_error"
        assert parsed["error"]["message"] == "something failed"

    def test_mk_error_with_retryable(self):
        result = mk_error("timeout", "connection timeout", retryable=True)
        parsed = json.loads(result)
        assert parsed["error"]["retryable"] is True



