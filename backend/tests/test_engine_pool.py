"""
Unit tests for backend/engine_pool.py (EnginePool).
"""

import asyncio
from typing import Optional
import pytest

from backend.engine_pool import EnginePool


class MockWorkerEngine:
    """Mock engine for testing EnginePool concurrency, FEN routing, and queue safety."""

    def __init__(self, engine_id: int, shared_state: dict):
        self.engine_id = engine_id
        self.shared_state = shared_state
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True

    def is_available(self) -> bool:
        return True

    async def analyze(
        self,
        fen: str,
        depth: Optional[int] = None,
        multipv: int = 1,
        time_limit: Optional[float] = None,
        nodes: Optional[int] = None,
    ) -> dict:
        async with self.shared_state["lock"]:
            self.shared_state["active"] += 1
            if self.shared_state["active"] > self.shared_state["max_active"]:
                self.shared_state["max_active"] = self.shared_state["active"]

        try:
            await asyncio.sleep(0.05)
            return {
                "fen": fen,
                "engine_id": self.engine_id,
                "evaluation": 100,
                "nodes": nodes or 1000,
                "multipv": multipv,
            }
        finally:
            async with self.shared_state["lock"]:
                self.shared_state["active"] -= 1

    async def get_policy_distribution(self, fen: str, nodes: int = 1) -> list[dict]:
        return [{"uci": "e2e4", "san": "e4", "p": 0.8, "fen": fen}]


@pytest.mark.anyio
async def test_engine_pool_concurrency_cap():
    """Test 1: 10 concurrent analyze calls on a 3-worker pool -> max concurrency == 3."""
    shared_state = {
        "active": 0,
        "max_active": 0,
        "lock": asyncio.Lock(),
    }
    counter = 0

    def factory():
        nonlocal counter
        counter += 1
        return MockWorkerEngine(counter, shared_state)

    pool = EnginePool(3, factory)
    await pool.start()

    fens = [f"rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 {i}" for i in range(10)]
    tasks = [pool.analyze(fen, nodes=500) for fen in fens]
    results = await asyncio.gather(*tasks)

    assert len(results) == 10
    assert shared_state["max_active"] == 3
    assert pool.n == 3

    await pool.stop()


@pytest.mark.anyio
async def test_engine_pool_no_cross_wiring():
    """Test 2: Results map to the correct FENs without cross-wiring."""
    shared_state = {
        "active": 0,
        "max_active": 0,
        "lock": asyncio.Lock(),
    }
    counter = 0

    def factory():
        nonlocal counter
        counter += 1
        return MockWorkerEngine(counter, shared_state)

    pool = EnginePool(4, factory)
    await pool.start()

    fens = [f"fen_spec_test_{i}" for i in range(10)]
    tasks = [pool.analyze(fen) for fen in fens]
    results = await asyncio.gather(*tasks)

    for i, res in enumerate(results):
        assert res["fen"] == f"fen_spec_test_{i}"

    await pool.stop()


@pytest.mark.anyio
async def test_engine_pool_n1_delegation():
    """Test 4: N=1 pool passes existing-behavior test (delegates transparently)."""
    shared_state = {
        "active": 0,
        "max_active": 0,
        "lock": asyncio.Lock(),
    }

    def factory():
        return MockWorkerEngine(1, shared_state)

    pool = EnginePool(1, factory)
    assert pool.n == 1
    assert pool.is_available()

    await pool.start()

    res = await pool.analyze("test_fen_n1", nodes=100)
    assert res["fen"] == "test_fen_n1"

    policy = await pool.get_policy_distribution("test_fen_n1")
    assert len(policy) == 1
    assert policy[0]["fen"] == "test_fen_n1"

    await pool.stop()


@pytest.mark.anyio
async def test_engine_pool_queue_exhaustion_timeout():
    """Test 3: Queue exhaustion when queue is not released will cause wait_for timeout."""
    shared_state = {
        "active": 0,
        "max_active": 0,
        "lock": asyncio.Lock(),
    }

    class NonReleasingPool(EnginePool):
        async def analyze_no_release(self, fen: str):
            eng = await self._queue.get()
            # Deliberately omit returning worker to queue
            return await eng.analyze(fen)

    def factory():
        return MockWorkerEngine(1, shared_state)

    pool = NonReleasingPool(1, factory)
    await pool.start()

    # First call consumes the only worker
    res1 = await pool.analyze_no_release("fen1")
    assert res1["fen"] == "fen1"

    # Second call must block and hit TimeoutError via asyncio.wait_for
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(pool.analyze_no_release("fen2"), timeout=0.1)

    await pool.stop()



@pytest.mark.anyio
async def test_engine_pool_forwards_none_depth_verbatim():
    # Guard for signature-drift: depth=None means "no depth cap" and must reach
    # the worker as None, NOT be dropped so the engine's default (20) kicks in.
    seen = {}

    class RecordingEngine:
        async def start(self): pass
        async def stop(self): pass
        def is_available(self): return True
        async def analyze(self, fen, depth=20, multipv=3, time_limit=2.0, nodes=None):
            seen.update(depth=depth, multipv=multipv, time_limit=time_limit, nodes=nodes)
            return {"evaluation": 0}

    from backend.engine_pool import EnginePool
    pool = EnginePool(1, RecordingEngine)
    await pool.analyze("8/8/8/8/8/8/8/K6k w - - 0 1", depth=None, multipv=2,
                       time_limit=3.0, nodes=None)
    assert seen["depth"] is None, f"depth=None was mangled to {seen['depth']!r}"
    assert seen["multipv"] == 2 and seen["time_limit"] == 3.0 and seen["nodes"] is None
