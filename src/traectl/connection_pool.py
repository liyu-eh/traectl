#!/usr/bin/env python3
"""CDP 连接池：管理持久 CDP 连接，支持最大连接数和空闲超时回收。"""

import asyncio
import logging
import time
from typing import Optional

from .cdp_client import CDPClient, ConnectionState
from .config import CDP_HOST, CDP_PORT

logger = logging.getLogger("traectl.pool")


class _PooledConnection:
    """池化连接包装，记录最后使用时间。"""

    def __init__(self, cdp: CDPClient, key: str):
        self.cdp = cdp
        self.key = key
        self.last_used = time.monotonic()
        self._in_use = False

    def mark_used(self) -> None:
        self.last_used = time.monotonic()

    @property
    def in_use(self) -> bool:
        return self._in_use


class ConnectionPool:
    """CDP 持久连接池。

    - 按 (host, port) 键复用连接
    - 支持最大连接数限制
    - 空闲超时自动回收
    - 线程安全（asyncio.Lock）
    """

    def __init__(
        self,
        max_connections: int = 10,
        idle_timeout: float = 300.0,
    ):
        self._max_connections = max_connections
        self._idle_timeout = idle_timeout
        self._pool: dict[str, _PooledConnection] = {}
        self._lock = asyncio.Lock()
        self._reclaim_task: Optional[asyncio.Task] = None

    @staticmethod
    def _make_key(host: str, port: int) -> str:
        return f"{host}:{port}"

    async def acquire(self, host: str = CDP_HOST, port: int = CDP_PORT) -> CDPClient:
        """从池中获取或创建一个已连接的 CDPClient。

        如果池中有该 key 的空闲连接则复用，否则新建。
        超过 max_connections 时先回收最久未使用的空闲连接。
        """
        key = self._make_key(host, port)
        async with self._lock:
            # 尝试复用已有空闲连接
            conn = self._pool.get(key)
            if conn is not None and not conn.in_use:
                # 检查连接是否仍然存活
                alive = await self._check_alive(conn.cdp)
                if alive:
                    conn._in_use = True
                    conn.mark_used()
                    logger.debug(f"连接池复用连接: {key}")
                    return conn.cdp
                else:
                    # 连接已死，移除
                    await self._safe_disconnect(conn.cdp)
                    del self._pool[key]

            # 超过最大连接数时，回收最久未使用的空闲连接
            if len(self._pool) >= self._max_connections:
                self._evict_idle()

            # 创建新连接
            cdp = CDPClient(host=host, port=port)
            await cdp.connect()
            conn = _PooledConnection(cdp, key)
            conn._in_use = True
            self._pool[key] = conn
            logger.debug(f"连接池新建连接: {key}")
            self._ensure_reclaim_task()
            return cdp

    async def release(self, cdp: CDPClient) -> None:
        """将连接归还到池中（不断开）。"""
        async with self._lock:
            for conn in self._pool.values():
                if conn.cdp is cdp:
                    conn._in_use = False
                    conn.mark_used()
                    logger.debug(f"连接池归还连接: {conn.key}")
                    return
        # 不在池中（不应发生），安全断开
        await self._safe_disconnect(cdp)

    async def close(self) -> None:
        """关闭池中所有连接并停止回收任务。"""
        if self._reclaim_task is not None:
            self._reclaim_task.cancel()
            try:
                await self._reclaim_task
            except asyncio.CancelledError:
                pass
            self._reclaim_task = None

        async with self._lock:
            for conn in list(self._pool.values()):
                await self._safe_disconnect(conn.cdp)
            self._pool.clear()
            logger.debug("连接池已关闭")

    async def _check_alive(self, cdp: CDPClient) -> bool:
        """检查 CDPClient 连接是否存活。"""
        try:
            if cdp._state != ConnectionState.CONNECTED:
                return False
            return await cdp.is_alive()
        except Exception:
            return False

    async def _safe_disconnect(self, cdp: CDPClient) -> None:
        """安全断开连接，忽略异常。"""
        try:
            await cdp.disconnect()
        except Exception:
            pass

    def _evict_idle(self) -> None:
        """回收最久未使用的空闲连接（调用者需持有锁）。"""
        idle_conns = [c for c in self._pool.values() if not c.in_use]
        if not idle_conns:
            # 全部在使用中，强制回收最旧的
            idle_conns = sorted(self._pool.values(), key=lambda c: c.last_used)
        else:
            idle_conns = sorted(idle_conns, key=lambda c: c.last_used)

        if idle_conns:
            victim = idle_conns[0]
            # 同步标记移除，异步断开稍后执行
            del self._pool[victim.key]
            asyncio.ensure_future(self._safe_disconnect(victim.cdp))
            logger.debug(f"连接池回收连接: {victim.key}")

    def _ensure_reclaim_task(self) -> None:
        """确保空闲回收任务在运行。"""
        if self._reclaim_task is None or self._reclaim_task.done():
            try:
                loop = asyncio.get_running_loop()
                self._reclaim_task = loop.create_task(self._reclaim_loop())
            except RuntimeError:
                pass

    async def _reclaim_loop(self) -> None:
        """定期回收空闲超时的连接。"""
        while True:
            await asyncio.sleep(60)
            try:
                await self._reclaim_idle()
            except Exception as e:
                logger.warning(f"连接池回收异常: {e}")

    async def _reclaim_idle(self) -> None:
        """回收所有空闲超时的连接。"""
        now = time.monotonic()
        async with self._lock:
            to_remove = []
            for key, conn in self._pool.items():
                if not conn.in_use and (now - conn.last_used) > self._idle_timeout:
                    to_remove.append(key)
            for key in to_remove:
                conn = self._pool.pop(key)
                await self._safe_disconnect(conn.cdp)
                logger.debug(f"连接池空闲回收: {key}")
            # 池为空时取消回收任务
            if not self._pool:
                if self._reclaim_task is not None:
                    self._reclaim_task.cancel()
                    self._reclaim_task = None

    @property
    def stats(self) -> dict:
        """返回连接池统计信息。"""
        total = len(self._pool)
        in_use = sum(1 for c in self._pool.values() if c.in_use)
        return {
            "total": total,
            "in_use": in_use,
            "idle": total - in_use,
            "max_connections": self._max_connections,
            "idle_timeout": self._idle_timeout,
        }


# 全局单例连接池
_global_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    """获取全局连接池单例。"""
    global _global_pool
    if _global_pool is None:
        _global_pool = ConnectionPool()
    return _global_pool


async def close_pool() -> None:
    """关闭全局连接池。"""
    global _global_pool
    if _global_pool is not None:
        await _global_pool.close()
        _global_pool = None
