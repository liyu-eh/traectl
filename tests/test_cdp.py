import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from traectl.cdp_client import CDPClient, ConnectionState


class MockWebSocket:
    def __init__(self, responses):
        self.responses = responses
        self.sent_messages = []
        self.closed = False

    async def send(self, message):
        self.sent_messages.append(message)

    async def recv(self):
        if not self.responses:
            raise asyncio.TimeoutError("no more responses")
        return self.responses.pop(0)

    async def close(self):
        self.closed = True

    async def ping(self):
        return True


def _build_response(msg_id, result_data=None, error_data=None, method_name="Test.method"):
    resp = {"id": msg_id}
    if result_data is not None:
        resp["result"] = result_data
    if error_data is not None:
        resp["error"] = error_data
    return json.dumps(resp)


@pytest.fixture
def mock_ws():
    return MockWebSocket([])


@pytest.fixture
def cdp_client():
    return CDPClient(host="127.0.0.1", port=9222)


class TestCDPSendMessage:
    def test_send_command_formats_message(self, cdp_client):
        ws = MockWebSocket([
            _build_response(1, {"value": "ok"}),
        ])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Runtime.evaluate", {"expression": "1+1"}, timeout=5)

        result = asyncio.run(_run())
        assert result == {"value": "ok"}
        assert len(ws.sent_messages) == 1
        sent = json.loads(ws.sent_messages[0])
        assert sent["id"] == 1
        assert sent["method"] == "Runtime.evaluate"
        assert sent["params"] == {"expression": "1+1"}

    def test_send_command_enforces_matching_id(self, cdp_client):
        ws = MockWebSocket([
            json.dumps({"id": 99, "result": {"wrong": True}}),
            _build_response(1, {"value": "correct"}),
        ])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Test.cmd", {}, timeout=5)

        result = asyncio.run(_run())
        assert result == {"value": "correct"}

    def test_send_command_skips_console_events(self, cdp_client):
        console_event = json.dumps({
            "method": "Console.messageAdded",
            "params": {"message": {"text": "hello"}},
        })
        ws = MockWebSocket([
            console_event,
            _build_response(1, {"value": "after_console"}),
        ])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Test.cmd", {}, timeout=5)

        result = asyncio.run(_run())
        assert result == {"value": "after_console"}
        assert len(cdp_client._console_messages) == 1
        assert cdp_client._console_messages[0] == {"text": "hello"}


class TestCDPReceiveMessage:
    def test_receive_timeout_raises(self, cdp_client):
        ws = MockWebSocket([])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Test.cmd", {}, timeout=0.5)

        with pytest.raises(TimeoutError):
            asyncio.run(_run())

    def test_receive_cdp_error_raises(self, cdp_client):
        ws = MockWebSocket([
            _build_response(1, error_data={"code": -32000, "message": "Something went wrong"}),
        ])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Test.cmd", {}, timeout=5)

        with pytest.raises(RuntimeError, match="Something went wrong"):
            asyncio.run(_run())

    def test_receive_without_id_is_skipped(self, cdp_client):
        ws = MockWebSocket([
            json.dumps({"method": "Page.loadEventFired", "params": {}}),
            _build_response(1, {"value": "after_event"}),
        ])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            return await cdp_client._send_command_locked("Test.cmd", {}, timeout=5)

        result = asyncio.run(_run())
        assert result == {"value": "after_event"}


class TestCDPConnectionState:
    def test_initial_state_is_disconnected(self, cdp_client):
        assert cdp_client.state == ConnectionState.DISCONNECTED

    def test_disconnect_clears_ws(self, cdp_client):
        ws = MockWebSocket([])
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        async def _run():
            await cdp_client.disconnect()

        asyncio.run(_run())
        assert cdp_client._ws is None
        assert cdp_client.state == ConnectionState.DISCONNECTED
        assert ws.closed is True
