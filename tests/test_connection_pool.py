#!/usr/bin/env python3
"""ConnectionPool 测试：连接复用、回收、超时、并发安全。

全部 Mock，不需要真实 Trae CN/CDP。
"""
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from traectl.connection_pool import ConnectionPool, get_pool, close_pool
from traectl.cdp_client import CDPClient, ConnectionState
from traectl.config import CDP_HOST, CDP_PORT


# ── 辅助函数 ──────────────────────────────────────────────

def _make_mock_cdp(state=ConnectionState.CONNECTED, host=CDP_HOST, port=CDP_PORT):
    """创建一个 Mock CDPClient。"""
    client = MagicMock(spec=CDPClient)
    client.host = host
    client.port = port
    client._state = state
    client.state = state
    client.connect = AsyncMock()
    client.disconnect = AsyncMock()
    client.is_alive = AsyncMock(return_value=True)

    # 模拟 connect 将状态切换为 CONNECTED
    async def _connect():
        client._state = ConnectionState.CONNECTED
        client.state = ConnectionState.CONNECTED
    client.connect.side_effect = _connect

    return client


def _default_key(host=CDP_HOST, port=CDP_PORT):
    return ConnectionPool._make_key(host, port)


def _factory_with(instances):
    """返回一个接受 (host, port) 的 side_effect 工厂。"""
    def _factory(host=CDP_HOST, port=CDP_PORT):
        return instances.pop(0)
    return _factory


# ── Fixtures ──────────────────────────────────────────────

@pytest.fixture
def pool():
    return ConnectionPool(max_connections=3, idle_timeout=60)


@pytest.fixture
def mock_cdp_class():
    """全局 patch traectl.connection_pool.CDPClient，返回 mock 实例。"""
    with patch("traectl.connection_pool.CDPClient") as mocked:
        yield mocked


# ══════════════════════════════════════════════════════════
# 连接池基础
# ══════════════════════════════════════════════════════════

class TestPoolBasics:
    def test_new_pool_stats(self):
        p = ConnectionPool(max_connections=5, idle_timeout=120)
        assert p.stats == {"total": 0, "in_use": 0, "idle": 0, "max_connections": 5, "idle_timeout": 120}


# ══════════════════════════════════════════════════════════
# acquire 流程
# ══════════════════════════════════════════════════════════

class TestAcquire:
    @pytest.mark.asyncio
    async def test_acquire_creates_new_connection(self, pool, mock_cdp_class):
        """空池 acquire → 新建连接并加入池。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp = await pool.acquire("127.0.0.1", 9224)

        mock_cdp_class.assert_called_once_with(host="127.0.0.1", port=9224)
        mock_instance.connect.assert_awaited_once()
        assert cdp is mock_instance
        assert pool.stats["total"] == 1
        assert pool.stats["in_use"] == 1

    @pytest.mark.asyncio
    async def test_acquire_reuses_existing_idle(self, pool, mock_cdp_class):
        """池中有空闲连接 → 复用不新建。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp1 = await pool.acquire(CDP_HOST, CDP_PORT)
        cdp1_id = id(cdp1)

        # 归还
        await pool.release(cdp1)

        # 再次 acquire，应复用同一实例
        cdp2 = await pool.acquire(CDP_HOST, CDP_PORT)
        assert id(cdp2) == cdp1_id
        # CDPClient 构造函数只被调了一次
        mock_cdp_class.assert_called_once()
        assert pool.stats["in_use"] == 1

    @pytest.mark.asyncio
    async def test_acquire_removes_dead_connection(self, pool, mock_cdp_class):
        """池中有空闲连接但已死 → 移除后新建。"""
        alive_instance = _make_mock_cdp()
        mock_cdp_class.return_value = alive_instance

        cdp1 = await pool.acquire(CDP_HOST, CDP_PORT)
        await pool.release(cdp1)

        # 让已入池的连接 is_alive 返回 False
        alive_instance.is_alive = AsyncMock(return_value=False)

        # 第二次 acquire：检查存活 → 死 → 移除旧 → 建新
        cdp2 = await pool.acquire(CDP_HOST, CDP_PORT)
        assert pool.stats["total"] == 1  # 旧被删，新被加，仍为 1
        alive_instance.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_acquire_evicts_when_at_max(self, pool, mock_cdp_class):
        """池满时 acquire → 回收最久未使用的连接。"""
        instances = [_make_mock_cdp(host=f"h{i}", port=i) for i in range(4)]
        mock_cdp_class.side_effect = _factory_with(instances)

        # 填满 3 个
        c1 = await pool.acquire("h1", 1)
        c2 = await pool.acquire("h2", 2)
        c3 = await pool.acquire("h3", 3)
        # 归还前两个
        await pool.release(c1)
        await pool.release(c2)

        # 第 4 个 acquire，max=3，应回收最旧的（c1）
        c4 = await pool.acquire("h4", 4)
        assert c4 is not None
        # _evict_idle 用的是 ensure_future（fire-and-forget），断开是异步的
        # 验证连接已从池中移除
        assert pool._pool.get("h1:1") is None
        assert pool.stats["total"] == 3

    @pytest.mark.asyncio
    async def test_acquire_evicts_all_in_use_force_oldest(self, pool, mock_cdp_class):
        """全部在用 + 到达上限 → 强制回收最旧的。"""
        instances = [_make_mock_cdp(host=f"h{i}", port=i) for i in range(4)]
        mock_cdp_class.side_effect = _factory_with(instances)

        # 全都在用（不 release）
        c1 = await pool.acquire("h1", 1)
        c2 = await pool.acquire("h2", 2)
        c3 = await pool.acquire("h3", 3)

        # 第 4 个触发回收
        c4 = await pool.acquire("h4", 4)
        assert c4 is not None
        # 最旧的 c1 应被从池中移除
        assert pool._pool.get("h1:1") is None


# ══════════════════════════════════════════════════════════
# release 流程
# ══════════════════════════════════════════════════════════

class TestRelease:
    @pytest.mark.asyncio
    async def test_release_marks_idle(self, pool, mock_cdp_class):
        """release 后将连接标记为空闲。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp = await pool.acquire(CDP_HOST, CDP_PORT)
        await pool.release(cdp)

        assert pool.stats["in_use"] == 0
        assert pool.stats["idle"] == 1

    @pytest.mark.asyncio
    async def test_release_not_in_pool_disconnects(self, pool, mock_cdp_class):
        """release 一个不在池中的连接 → 安全断开（不应抛异常）。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp = await pool.acquire(CDP_HOST, CDP_PORT)
        # 清空池（模拟池被关闭后，连接不在池中）
        await pool.close()
        # cdp 已被 close 断开，但仍然在变量中
        # release 一个不在池中的连接，应 _safe_disconnect
        await pool.release(cdp)
        mock_instance.disconnect.assert_awaited()

    @pytest.mark.asyncio
    async def test_release_updates_timestamp(self, pool, mock_cdp_class):
        """release 后更新 last_used 时间戳。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp = await pool.acquire(CDP_HOST, CDP_PORT)
        t0 = time.monotonic()
        await asyncio.sleep(0.01)
        await pool.release(cdp)

        key = _default_key()
        conn = pool._pool.get(key)
        assert conn is not None, f"Key '{key}' not in pool"
        assert conn.last_used > t0


# ══════════════════════════════════════════════════════════
# close 流程
# ══════════════════════════════════════════════════════════

class TestClose:
    @pytest.mark.asyncio
    async def test_close_clears_pool(self, pool, mock_cdp_class):
        """close 后池为空，所有连接断开。"""
        instances = [_make_mock_cdp(host=f"h{i}", port=i) for i in range(3)]
        mock_cdp_class.side_effect = _factory_with(instances)

        await pool.acquire("h1", 1)
        await pool.acquire("h2", 2)
        await pool.acquire("h3", 3)
        await pool.close()

        assert pool._pool == {}

    @pytest.mark.asyncio
    async def test_close_cancels_reclaim_task(self, pool, mock_cdp_class):
        """close 后回收任务被取消。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        await pool.acquire(CDP_HOST, CDP_PORT)
        assert pool._reclaim_task is not None
        assert not pool._reclaim_task.done()

        await pool.close()
        assert pool._reclaim_task is None or pool._reclaim_task.done()

    @pytest.mark.asyncio
    async def test_close_idempotent(self, pool):
        """close 两次不应抛异常。"""
        await pool.close()
        await pool.close()


# ══════════════════════════════════════════════════════════
# 空闲回收
# ══════════════════════════════════════════════════════════

class TestIdleReclaim:
    @pytest.mark.asyncio
    async def test_reclaim_idle_removes_expired(self, pool, mock_cdp_class):
        """超过 idle_timeout 的连接被回收。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        cdp = await pool.acquire(CDP_HOST, CDP_PORT)
        await pool.release(cdp)

        key = _default_key()
        # 手动让 last_used 过期
        conn = pool._pool.get(key)
        assert conn is not None
        conn.last_used = 0  # epoch → 肯定过期

        await pool._reclaim_idle()

        assert key not in pool._pool
        mock_instance.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_reclaim_idle_skips_in_use(self, pool, mock_cdp_class):
        """正在使用的连接不会被回收。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        await pool.acquire(CDP_HOST, CDP_PORT)  # in_use=True, 未 release

        key = _default_key()
        conn = pool._pool.get(key)
        assert conn is not None
        conn.last_used = 0

        await pool._reclaim_idle()

        # 仍在池中
        assert key in pool._pool
        mock_instance.disconnect.assert_not_called()

    @pytest.mark.asyncio
    async def test_reclaim_loop_cancels_when_pool_empty(self, pool, mock_cdp_class):
        """池为空时回收任务停止。"""
        mock_instance = _make_mock_cdp()
        mock_cdp_class.return_value = mock_instance

        await pool.acquire(CDP_HOST, CDP_PORT)
        assert pool._reclaim_task is not None
        await pool.close()
        assert pool._reclaim_task is None or pool._reclaim_task.done()

    def test_evict_idle_removes_oldest(self, pool):
        """_evict_idle 移除最久未使用的空闲连接。"""
        from traectl.connection_pool import _PooledConnection
        c1 = _PooledConnection(_make_mock_cdp(), "a")
        c2 = _PooledConnection(_make_mock_cdp(), "b")
        c3 = _PooledConnection(_make_mock_cdp(), "c")
        c1.last_used = 100
        c2.last_used = 200
        c3.last_used = 300

        pool._pool = {"a": c1, "b": c2, "c": c3}
        with patch("asyncio.ensure_future"):
            pool._evict_idle()

        # 最旧的 c1 被移除
        assert len(pool._pool) == 2

    def test_evict_idle_all_in_use_removes_oldest(self, pool):
        """所有都在用 → 强制回收最旧的（按 last_used）。"""
        from traectl.connection_pool import _PooledConnection
        c1 = _PooledConnection(_make_mock_cdp(), "a")
        c2 = _PooledConnection(_make_mock_cdp(), "b")
        c1._in_use = True
        c2._in_use = True
        c1.last_used = 100
        c2.last_used = 200

        pool._pool = {"a": c1, "b": c2}
        with patch("asyncio.ensure_future"):
            pool._evict_idle()

        # c1 更旧，被移除
        assert "a" not in pool._pool


# ══════════════════════════════════════════════════════════
# 全局单例
# ══════════════════════════════════════════════════════════

class TestGlobalSingleton:
    def setup_method(self):
        import traectl.connection_pool as cp
        cp._global_pool = None

    def test_get_pool_returns_singleton(self):
        p1 = get_pool()
        p2 = get_pool()
        assert p1 is p2

    @pytest.mark.asyncio
    async def test_close_pool_clears_singleton(self):
        p = get_pool()
        assert p is not None
        await close_pool()
        import traectl.connection_pool as cp
        assert cp._global_pool is None
