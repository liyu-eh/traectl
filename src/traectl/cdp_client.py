#!/usr/bin/env python3
"""CDP WebSocket 客户端：线程安全的 Chrome DevTools Protocol 通信层。"""

import asyncio
import base64
import json
import logging
import random
import time
import urllib.request
from typing import Any, Optional

import websockets
from websockets.exceptions import ConnectionClosed

from .config import (
    CDP_HOST,
    CDP_PORT,
    INITIAL_RETRY_INTERVAL,
    MAX_RETRIES,
    MAX_RETRY_INTERVAL,
)

logger = logging.getLogger("traectl.cdp")


class ConnectionState:
    """CDP 连接状态枚举。"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"


class CDPClient:
    """底层 CDP WebSocket 客户端，提供线程安全的 eval 和截图。

    特性：
    - 连接状态机：disconnected → connecting → connected
    - 指数退避重连（1s, 2s, ..., max 30s）
    - 所有操作自动检测断连并触发重连
    - 线程安全的 _msg_id 管理
    """

    def __init__(self, host: str = CDP_HOST, port: int = CDP_PORT):
        self._host = host
        self._port = port
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._msg_id = 0
        self._target_id: Optional[str] = None
        self._lock = asyncio.Lock()
        self._state = ConnectionState.DISCONNECTED
        self._retry_count = 0
        self._last_connect_time = 0.0
        self._console_messages: list[dict] = []
        self._console_enabled = False

    @property
    def state(self) -> str:
        return self._state

    @property
    def host(self) -> str:
        return self._host

    @property
    def port(self) -> int:
        return self._port

    async def is_alive(self) -> bool:
        """安全检查 WebSocket 是否仍存活。"""
        if not self._ws:
            return False
        try:
            await asyncio.wait_for(self._ws.ping(), timeout=3)
            return True
        except Exception:
            return False

    # -- 连接管理 --

    async def _exponential_backoff(self) -> None:
        """指数退避等待（含随机抖动）。"""
        delay = min(
            INITIAL_RETRY_INTERVAL * (2 ** self._retry_count),
            MAX_RETRY_INTERVAL,
        )
        jitter = delay * random.uniform(-0.25, 0.25)
        wait = delay + jitter
        logger.info(f"CDP 重连退避: attempt={self._retry_count + 1}, delay={wait:.1f}s")
        await asyncio.sleep(wait)

    async def connect(self) -> None:
        """建立 CDP 连接（含重试和指数退避）。"""
        self._state = ConnectionState.CONNECTING

        for attempt in range(MAX_RETRIES):
            url = f"http://{self._host}:{self._port}/json/list"
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:
                    tabs = json.loads(resp.read())
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"CDP 连接失败 ({url}): {e}，准备重试")
                    self._retry_count = attempt
                    await self._exponential_backoff()
                    continue
                self._state = ConnectionState.DISCONNECTED
                raise RuntimeError(f"无法连接 CDP ({url}): {e}") from e

            # 三级降级策略匹配 Trae 页面
            for tab in tabs:
                title = tab.get("title", "")
                if "Trae" in title and tab.get("type") == "page":
                    tab_url = tab.get("url", "")
                    if "vscode-file" in tab_url:
                        self._target_id = tab["id"]
                        break

            if not self._target_id:
                for tab in tabs:
                    title = tab.get("title", "")
                    if "Trae" in title and tab.get("type") == "page":
                        self._target_id = tab["id"]
                        logger.info(f"CDP 通过标题匹配 Trae 页面: {title[:40]}...")
                        break

            if not self._target_id:
                for tab in tabs:
                    if tab.get("type") == "page":
                        self._target_id = tab["id"]
                        logger.warning(f"CDP 未找到 Trae 特定页面，回退到: {tab.get('title', 'unknown')[:40]}...")
                        break

            if not self._target_id:
                available = [(t.get("title", ""), t.get("url", "")[:60]) for t in tabs]
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"CDP 无可用页面 (attempt {attempt + 1})，可用: {available}")
                    self._retry_count = attempt
                    await self._exponential_backoff()
                    continue
                self._state = ConnectionState.DISCONNECTED
                raise RuntimeError(f"CDP 无可用页面。当前标签: {available}")

            ws_url = f"ws://{self._host}:{self._port}/devtools/page/{self._target_id}"
            try:
                self._ws = await websockets.connect(ws_url, max_size=50 * 1024 * 1024)
            except Exception as e:
                if attempt < MAX_RETRIES - 1:
                    logger.warning(f"WebSocket 连接失败: {e}，准备重试")
                    self._retry_count = attempt
                    await self._exponential_backoff()
                    continue
                self._state = ConnectionState.DISCONNECTED
                raise RuntimeError(f"WebSocket 连接失败 ({ws_url}): {e}") from e

            # 连接成功
            self._state = ConnectionState.CONNECTED
            self._retry_count = 0
            self._last_connect_time = time.monotonic()
            logger.info(f"CDP 已连接: target={self._target_id[:16]}...")
            return

    async def disconnect(self) -> None:
        """断开 CDP 连接。"""
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None
        self._state = ConnectionState.DISCONNECTED

    async def ensure_connected(self) -> None:
        """确保连接可用 —— 不可用时自动重连（带指数退避）。"""
        if self._state == ConnectionState.CONNECTING:
            for _ in range(30):
                await asyncio.sleep(0.5)
                if self._state != ConnectionState.CONNECTING:
                    break
            if self._state != ConnectionState.CONNECTED:
                raise RuntimeError("CDP 连接超时（其他协程正在连接但未完成）")
            return

        if self._state == ConnectionState.CONNECTED and self._ws:
            try:
                alive = await asyncio.wait_for(self._ws.ping(), timeout=3)
                if alive:
                    return
            except Exception:
                logger.warning("CDP ping 失败，准备重连")

        logger.info("CDP 断连，开始重连...")
        await self.disconnect()
        await self.connect()

    # -- 核心 CDP 通信 --

    async def send_command(self, method: str, params: Optional[dict] = None, timeout: float = 10) -> dict:
        """通用 CDP 方法调用器。

        发送 {"id": msg_id, "method": method, "params": params}，
        循环 recv 等待匹配 id 的响应，返回 result 字典。
        收集 Console.messageAdded 事件到 _console_messages。
        """
        for attempt in range(3):
            try:
                await self.ensure_connected()
                async with self._lock:
                    return await self._send_command_locked(method, params or {}, timeout)
            except (ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning(f"send_command 连接异常 (attempt {attempt + 1}): {e}")
                self._state = ConnectionState.DISCONNECTED
                await asyncio.sleep(0.5)
                continue
            except Exception:
                raise
        raise RuntimeError(f"send_command {method} 在 3 次尝试后仍失败")

    async def _send_command_locked(self, method: str, params: dict, timeout: float) -> dict:
        """已持有锁的 send_command 实现。"""
        self._msg_id += 1
        msg_id = self._msg_id

        await self._ws.send(json.dumps({
            "id": msg_id,
            "method": method,
            "params": params,
        }))

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            resp = json.loads(
                await asyncio.wait_for(self._ws.recv(), timeout=max(remaining, 0.1))
            )
            # 收集 console 事件
            if "method" in resp and resp.get("method") == "Console.messageAdded":
                params_data = resp.get("params", {})
                msg = params_data.get("message", {})
                if msg:
                    self._console_messages.append(msg)
                continue
            if "id" not in resp:
                continue
            if resp["id"] != msg_id:
                continue
            if "error" in resp:
                err = resp["error"]
                raise RuntimeError(f"CDP {method} 错误: {err}")
            return resp.get("result", {})
        raise TimeoutError(f"CDP {method} 超时 ({timeout}s)")

    # -- Runtime / JS eval --

    async def eval_js(self, expression: str, timeout: float = 10) -> Any:
        """在 Trae CN 页面中执行 JavaScript 并返回结果。"""
        result = await self.send_command("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": False,
        }, timeout=timeout)
        if "exceptionDetails" in result:
            exc = result["exceptionDetails"]
            desc = exc.get("exception", {}).get("description", str(exc))
            raise RuntimeError(f"JS 执行异常: {desc}")
        value_result = result.get("result", {})
        if value_result.get("type") == "string":
            return value_result.get("value", "")
        return value_result.get("value")

    # -- 截图 --

    async def capture_screenshot(self) -> str:
        """截取界面截图，返回 base64 编码的 PNG 数据。"""
        result = await self.send_command("Page.captureScreenshot", {
            "format": "png",
            "fromSurface": True,
        }, timeout=15)
        data = result.get("data", "")
        if not data:
            raise RuntimeError("截图返回空数据")
        return data

    # -- Page 操作 --

    async def navigate(self, url: str, timeout: float = 30) -> dict:
        """导航到指定 URL。"""
        return await self.send_command("Page.navigate", {"url": url}, timeout=timeout)

    async def reload_page(self, ignore_cache: bool = False) -> dict:
        """重新加载页面。"""
        return await self.send_command("Page.reload", {"ignoreCache": ignore_cache})

    async def print_to_pdf(self) -> bytes:
        """将页面打印为 PDF，返回 PDF 字节数据。"""
        result = await self.send_command("Page.printToPDF", {}, timeout=30)
        data = result.get("data", "")
        if not data:
            raise RuntimeError("PDF 返回空数据")
        return base64.b64decode(data)

    async def get_navigation_history(self) -> dict:
        """获取页面导航历史。"""
        return await self.send_command("Page.getNavigationHistory", {})

    async def navigate_to_history_entry(self, entry_id: int) -> dict:
        """导航到历史记录中的指定条目。"""
        return await self.send_command("Page.navigateToHistoryEntry", {"entryId": entry_id})

    async def set_download_behavior(self, behavior: str, download_path: str = "") -> dict:
        """设置下载行为。"""
        params: dict[str, Any] = {"behavior": behavior}
        if download_path:
            params["downloadPath"] = download_path
        return await self.send_command("Page.setDownloadBehavior", params)

    # -- DOM 操作 --

    async def get_document(self, depth: int = -1) -> dict:
        """获取页面 DOM 文档。"""
        params: dict[str, Any] = {}
        if depth >= 0:
            params["depth"] = depth
        return await self.send_command("DOM.getDocument", params)

    async def query_selector(self, node_id: int, selector: str) -> int:
        """在指定节点下查询单个元素，返回 nodeId（0 表示未找到）。"""
        result = await self.send_command("DOM.querySelector", {
            "nodeId": node_id,
            "selector": selector,
        })
        return result.get("nodeId", 0)

    async def query_selector_all(self, node_id: int, selector: str) -> list[int]:
        """在指定节点下查询所有匹配元素，返回 nodeId 列表。"""
        result = await self.send_command("DOM.querySelectorAll", {
            "nodeId": node_id,
            "selector": selector,
        })
        return result.get("nodeIds", [])

    async def get_outer_html(self, node_id: int) -> str:
        """获取指定节点的外部 HTML。"""
        result = await self.send_command("DOM.getOuterHTML", {"nodeId": node_id})
        return result.get("outerHTML", "")

    async def get_box_model(self, node_id: int) -> dict:
        """获取指定节点的盒模型（content, padding, border, margin）。"""
        return await self.send_command("DOM.getBoxModel", {"nodeId": node_id})

    async def scroll_into_view_if_needed(self, node_id: int) -> dict:
        """将指定节点滚动到可视区域。"""
        return await self.send_command("DOM.scrollIntoViewIfNeeded", {"nodeId": node_id})

    async def resolve_node(self, node_id: int) -> dict:
        """将 nodeId 解析为 Runtime.RemoteObject。"""
        return await self.send_command("DOM.resolveNode", {"nodeId": node_id})

    async def request_child_nodes(self, node_id: int, depth: int = -1) -> list[dict]:
        """请求指定节点的子节点列表。"""
        params: dict[str, Any] = {"nodeId": node_id}
        if depth >= 0:
            params["depth"] = depth
        result = await self.send_command("DOM.requestChildNodes", params)
        return result.get("nodes", [])

    # -- 增强输入 --

    async def insert_text(self, text: str) -> dict:
        """使用 Input.insertText 插入文本（比按键更可靠）。"""
        return await self.send_command("Input.insertText", {"text": text})

    async def type_text(self, text: str, el_node_id: Optional[int] = None) -> dict:
        """聚焦元素并插入文本。如果提供了 el_node_id，先聚焦该元素。"""
        if el_node_id is not None:
            await self.send_command("DOM.focus", {"nodeId": el_node_id})
        return await self.insert_text(text)

    async def mouse_double_click(self, x: int, y: int) -> None:
        """在指定坐标双击。"""
        async with self._lock:
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mouseMoved", x, y)
            await asyncio.sleep(0.05)
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mousePressed", x, y, click_count=2)
            await asyncio.sleep(0.05)
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mouseReleased", x, y, click_count=2)
            await self._drain_mouse_responses()

    async def mouse_drag(self, x1: int, y1: int, x2: int, y2: int, steps: int = 5) -> None:
        """从 (x1, y1) 拖拽到 (x2, y2)。"""
        async with self._lock:
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mouseMoved", x1, y1)
            await asyncio.sleep(0.05)
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mousePressed", x1, y1)
            await asyncio.sleep(0.05)
            for i in range(1, steps + 1):
                t = i / steps
                mx = int(x1 + (x2 - x1) * t)
                my = int(y1 + (y2 - y1) * t)
                self._msg_id += 1
                await self._dispatch_mouse_event(self._msg_id, "mouseMoved", mx, my)
                await asyncio.sleep(0.02)
            self._msg_id += 1
            await self._dispatch_mouse_event(self._msg_id, "mouseReleased", x2, y2)
            await self._drain_mouse_responses()

    async def mouse_move(self, x: int, y: int, steps: int = 1) -> None:
        """移动鼠标到指定坐标。"""
        async with self._lock:
            for i in range(1, steps + 1):
                self._msg_id += 1
                await self._dispatch_mouse_event(self._msg_id, "mouseMoved", x, y)
                await asyncio.sleep(0.02)

    async def _dispatch_mouse_event(self, msg_id: int, event_type: str, x: int, y: int, click_count: int = 0) -> None:
        """发送单个鼠标事件。调用者须在 self._lock 内自增 _msg_id 并传入 msg_id。"""
        params: dict[str, Any] = {"type": event_type, "x": x, "y": y}
        if click_count:
            params["button"] = "left"
            params["clickCount"] = click_count
            params["pointerType"] = "mouse"
        await self._ws.send(json.dumps({
            "id": msg_id,
            "method": "Input.dispatchMouseEvent",
            "params": params,
        }))

    async def scroll_by(self, delta_x: int = 0, delta_y: int = 0) -> Any:
        """通过 wheel 事件滚动页面。"""
        async with self._lock:
            self._msg_id += 1
            await self._ws.send(json.dumps({
                "id": self._msg_id,
                "method": "Input.dispatchMouseEvent",
                "params": {
                    "type": "mouseWheel",
                    "x": 0,
                    "y": 0,
                    "deltaX": delta_x,
                    "deltaY": delta_y,
                },
            }))
            await self._drain_mouse_responses()
        return {"scrolled": True, "deltaX": delta_x, "deltaY": delta_y}

    async def scroll_to(self, x: int, y: int) -> Any:
        """通过 JS 将页面滚动到指定位置。"""
        return await self.eval_js(f"window.scrollTo({x}, {y})")

    # -- 网络操作 --

    async def get_cookies(self, urls: Optional[list[str]] = None) -> list[dict]:
        """获取 Cookie 列表。"""
        params: dict[str, Any] = {}
        if urls:
            params["urls"] = urls
        result = await self.send_command("Network.getCookies", params)
        return result.get("cookies", [])

    async def set_cookie(self, name: str, value: str, url: Optional[str] = None, domain: Optional[str] = None) -> bool:
        """设置 Cookie。"""
        params: dict[str, Any] = {"name": name, "value": value}
        if url:
            params["url"] = url
        if domain:
            params["domain"] = domain
        result = await self.send_command("Network.setCookie", params)
        return result.get("success", False)

    async def delete_cookies(self, name: str, url: Optional[str] = None, domain: Optional[str] = None) -> dict:
        """删除指定 Cookie。"""
        params: dict[str, Any] = {"name": name}
        if url:
            params["url"] = url
        if domain:
            params["domain"] = domain
        return await self.send_command("Network.deleteCookies", params)

    async def clear_browser_cache(self) -> dict:
        """清除浏览器缓存。"""
        return await self.send_command("Network.clearBrowserCache", {})

    async def clear_browser_cookies(self) -> dict:
        """清除所有浏览器 Cookie。"""
        return await self.send_command("Network.clearBrowserCookies", {})

    async def set_extra_http_headers(self, headers: dict[str, str]) -> dict:
        """设置额外的 HTTP 请求头。"""
        return await self.send_command("Network.setExtraHTTPHeaders", {"headers": headers})

    # -- Target 管理 --

    async def list_targets(self) -> list[dict]:
        """列出所有目标（标签页）。"""
        result = await self.send_command("Target.getTargets", {})
        return result.get("targetInfos", [])

    async def activate_target(self, target_id: str) -> dict:
        """激活（切换到）指定目标。"""
        return await self.send_command("Target.activateTarget", {"targetId": target_id})

    async def close_target(self, target_id: str) -> bool:
        """关闭指定目标。"""
        result = await self.send_command("Target.closeTarget", {"targetId": target_id})
        return result.get("success", False)

    async def create_target(self, url: str) -> str:
        """创建新目标（标签页），返回 targetId。"""
        result = await self.send_command("Target.createTarget", {"url": url})
        return result.get("targetId", "")

    # -- Emulation --

    async def set_device_metrics(self, width: int, height: int, scale_factor: float = 1.0, mobile: bool = False) -> dict:
        """设置设备视口指标。"""
        return await self.send_command("Emulation.setDeviceMetricsOverride", {
            "width": width,
            "height": height,
            "deviceScaleFactor": scale_factor,
            "mobile": mobile,
        })

    async def set_user_agent(self, user_agent: str, platform: Optional[str] = None) -> dict:
        """设置 User-Agent。"""
        params: dict[str, Any] = {"userAgent": user_agent}
        if platform:
            params["platform"] = platform
        return await self.send_command("Emulation.setUserAgentOverride", params)

    async def set_geolocation(self, lat: float, lng: float, accuracy: float = 100) -> dict:
        """设置地理位置。"""
        return await self.send_command("Emulation.setGeolocationOverride", {
            "latitude": lat,
            "longitude": lng,
            "accuracy": accuracy,
        })

    async def reset_emulation(self) -> dict:
        """重置所有 Emulation 覆盖。"""
        await self.send_command("Emulation.clearDeviceMetricsOverride", {})
        await self.send_command("Emulation.clearGeolocationOverride", {})
        return {"status": "reset"}

    # -- Console 捕获 --

    async def enable_console(self) -> dict:
        """启用 Console 消息捕获。"""
        self._console_enabled = True
        return await self.send_command("Console.enable", {})

    async def disable_console(self) -> dict:
        """禁用 Console 消息捕获。"""
        self._console_enabled = False
        return await self.send_command("Console.disable", {})

    async def get_console_messages(self) -> list[dict]:
        """获取已收集的 Console 消息列表。"""
        messages = self._console_messages.copy()
        self._console_messages.clear()
        return messages

    # -- Performance --

    async def get_metrics(self) -> list[dict]:
        """获取性能指标。"""
        result = await self.send_command("Performance.getMetrics", {})
        return result.get("metrics", [])

    # -- 工具方法 --

    async def wait_for_selector(self, selector: str, timeout: float = 10) -> bool:
        """轮询等待指定 CSS 选择器匹配到元素。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            found = await self.eval_js(
                f"!!document.querySelector({json.dumps(selector)})", timeout=2
            )
            if found:
                return True
            await asyncio.sleep(0.5)
        return False

    async def get_element_rect(self, selector: str) -> dict:
        """获取指定 CSS 选择器匹配元素的位置和尺寸。"""
        result = await self.eval_js(f"""
            (function() {{
                var el = document.querySelector({json.dumps(selector)});
                if (!el) return null;
                var rect = el.getBoundingClientRect();
                return {{
                    x: rect.x + window.scrollX,
                    y: rect.y + window.scrollY,
                    width: rect.width,
                    height: rect.height,
                    top: rect.top,
                    left: rect.left,
                    right: rect.right,
                    bottom: rect.bottom
                }};
            }})()
        """, timeout=5)
        if result is None:
            raise RuntimeError(f"未找到元素: {selector}")
        return result

    # -- 原有低级输入方法（保留） --

    async def dispatch_key_event(self, key: str, code: str, event_type: str = "keyDown", modifiers: int = 0) -> None:
        """发送单个键盘事件。"""
        async with self._lock:
            self._msg_id += 1
            await self._ws.send(json.dumps({
                "id": self._msg_id,
                "method": "Input.dispatchKeyEvent",
                "params": {
                    "type": event_type,
                    "key": key,
                    "code": code,
                    "modifiers": modifiers,
                    "windowsVirtualKeyCode": 0,
                },
            }))

    async def dispatch_key_combo(self, keys: list) -> None:
        """发送键盘组合键（如 ['Control', 'Shift', 'KeyP']）。"""
        modifier_map = {"Control": 2, "Shift": 8, "Alt": 1, "Meta": 4}
        mods = sum(modifier_map.get(k, 0) for k in keys)
        # 按下修饰键
        for key in keys:
            if key in modifier_map:
                await self.dispatch_key_event(key, key, "keyDown", mods)
        # 按下并释放最后一个非修饰键
        main_key = None
        for key in keys:
            if key not in modifier_map:
                main_key = key
                break
        if main_key:
            await self.dispatch_key_event(main_key, main_key, "keyDown", mods)
            await asyncio.sleep(0.05)
            await self.dispatch_key_event(main_key, main_key, "keyUp", mods)
        # 释放修饰键（逆序）
        for key in reversed(keys):
            if key in modifier_map:
                await self.dispatch_key_event(key, key, "keyUp", 0)
        await asyncio.sleep(0.1)

    async def dispatch_mouse_click(self, x: int, y: int) -> None:
        """用 CDP 原生鼠标事件点击指定坐标。"""
        async with self._lock:
            self._msg_id += 1
            await self._ws.send(json.dumps({
                "id": self._msg_id,
                "method": "Input.dispatchMouseEvent",
                "params": {"type": "mouseMoved", "x": x, "y": y},
            }))
            await asyncio.sleep(0.1)

            self._msg_id += 1
            await self._ws.send(json.dumps({
                "id": self._msg_id,
                "method": "Input.dispatchMouseEvent",
                "params": {
                    "type": "mousePressed", "x": x, "y": y,
                    "button": "left", "clickCount": 1, "pointerType": "mouse",
                },
            }))
            await asyncio.sleep(0.05)

            self._msg_id += 1
            await self._ws.send(json.dumps({
                "id": self._msg_id,
                "method": "Input.dispatchMouseEvent",
                "params": {
                    "type": "mouseReleased", "x": x, "y": y,
                    "button": "left", "clickCount": 1, "pointerType": "mouse",
                },
            }))

            await self._drain_mouse_responses()

    async def _drain_mouse_responses(self) -> None:
        """排空鼠标事件后的 CDP 响应。"""
        for _ in range(5):
            try:
                await asyncio.wait_for(self._ws.recv(), timeout=0.3)
            except (asyncio.TimeoutError, Exception):
                break
