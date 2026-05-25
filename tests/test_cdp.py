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


# ══════════════════════════════════════════════════════════
# ensure_connected 重连逻辑
# ══════════════════════════════════════════════════════════

class TestEnsureConnected:
    """验证 CDP 自动重连逻辑的完整状态机。"""

    @pytest.mark.asyncio
    async def test_alive_connected_noop(self, cdp_client):
        """已连接且 alive → 不做任何事。"""
        ws = AsyncMock()
        ws.ping = AsyncMock(return_value=True)
        ws.close = AsyncMock()
        cdp_client._ws = ws
        cdp_client._state = ConnectionState.CONNECTED

        with patch.object(cdp_client, 'connect', new=AsyncMock()) as mock_connect:
            await cdp_client.ensure_connected()

        mock_connect.assert_not_called()
        ws.ping.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connected_but_ping_fails_reconnects(self, cdp_client):
        """已连接但 ping 失败 → 重连。"""
        old_ws = AsyncMock()
        old_ws.ping = AsyncMock(side_effect=Exception("ping fail"))
        old_ws.close = AsyncMock()
        cdp_client._ws = old_ws
        cdp_client._state = ConnectionState.CONNECTED

        with patch.object(cdp_client, 'connect', new=AsyncMock()) as mock_connect, \
             patch.object(cdp_client, 'disconnect', new=AsyncMock()) as mock_disconnect:
            await cdp_client.ensure_connected()

        mock_disconnect.assert_awaited_once()
        mock_connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnected_reconnects(self, cdp_client):
        """断连状态 → 重连。"""
        cdp_client._ws = None
        cdp_client._state = ConnectionState.DISCONNECTED

        with patch.object(cdp_client, 'connect', new=AsyncMock()) as mock_connect, \
             patch.object(cdp_client, 'disconnect', new=AsyncMock()) as mock_disconnect:
            await cdp_client.ensure_connected()

        mock_disconnect.assert_awaited_once()
        mock_connect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_connecting_waits_then_returns(self, cdp_client):
        """正在连接中 → 等待直到连接完成。"""
        cdp_client._ws = None
        cdp_client._state = ConnectionState.CONNECTING

        # 模拟另一个协程在 0.3s 后将状态切换为 CONNECTED
        async def _set_connected():
            await asyncio.sleep(0.3)
            cdp_client._state = ConnectionState.CONNECTED

        async with asyncio.TaskGroup() as tg:
            tg.create_task(_set_connected())
            tg.create_task(cdp_client.ensure_connected())

        assert cdp_client._state == ConnectionState.CONNECTED

    @pytest.mark.asyncio
    async def test_connecting_timeout_raises(self, cdp_client):
        """连接中超时 → 抛出 RuntimeError。"""
        cdp_client._ws = None
        cdp_client._state = ConnectionState.CONNECTING

        with pytest.raises(RuntimeError, match="CDP 连接超时"):
            await cdp_client.ensure_connected()

    @pytest.mark.asyncio
    async def test_no_ws_but_connected_state_reconnects(self, cdp_client):
        """state=CONNECTED 但 ws=None → ping 失败 → 重连。"""
        cdp_client._ws = None
        cdp_client._state = ConnectionState.CONNECTED

        with patch.object(cdp_client, 'connect', new=AsyncMock()) as mock_connect, \
             patch.object(cdp_client, 'disconnect', new=AsyncMock()) as mock_disconnect:
            await cdp_client.ensure_connected()

        mock_disconnect.assert_awaited_once()
        mock_connect.assert_awaited_once()
