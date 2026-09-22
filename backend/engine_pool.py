"""
EnginePool: N LC0Engine workers behind the same duck-type interface as one engine.

Provides position-level parallelism for LC0 analyses. N=1 (default) behaves
identically to a single LC0Engine instance.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class EnginePool:
    """N LC0Engine workers behind the same duck-type interface as one engine.
    N=1 (default) must be byte-for-byte the behavior of a single LC0Engine.
    """

    def __init__(self, n: int, engine_factory: Callable[[], Any]) -> None:
        if n < 1:
            raise ValueError(f"EnginePool size n must be >= 1, got {n}")
        self.n: int = n
        self._workers: list = [engine_factory() for _ in range(n)]
        self._queue: asyncio.Queue = asyncio.Queue()
        for worker in self._workers:
            self._queue.put_nowait(worker)

    async def start(self) -> None:
        """Start all worker engines concurrently."""
        await asyncio.gather(*(w.start() for w in self._workers))

    async def stop(self) -> None:
        """Stop all worker engines concurrently."""
        await asyncio.gather(*(w.stop() for w in self._workers))

    def is_available(self) -> bool:
        """Return True if any worker engine is available."""
        return any(w.is_available() for w in self._workers)

    async def analyze(
        self,
        fen: str,
        depth: Optional[int] = 20,
        multipv: int = 3,
        time_limit: float = 2.0,
        nodes: Optional[int] = None,
    ) -> dict:
        """Analyze a position using an available worker engine from the pool.

        Signature and defaults mirror LC0Engine.analyze EXACTLY, and every
        argument is forwarded verbatim — including depth=None, which means
        "no depth cap" in the time-based path. (An earlier draft dropped None
        args, silently turning depth=None into the engine's default depth=20:
        classic signature-drift.)"""
        eng = await self._queue.get()
        try:
            return await eng.analyze(fen, depth=depth, multipv=multipv,
                                     time_limit=time_limit, nodes=nodes)
        finally:
            self._queue.put_nowait(eng)

    async def get_policy_distribution(self, fen: str, nodes: int = 1) -> list[dict]:
        """Fetch policy distribution using an available worker engine from the pool."""
        eng = await self._queue.get()
        try:
            return await eng.get_policy_distribution(fen, nodes=nodes)
        finally:
            self._queue.put_nowait(eng)

    async def search_lines(self, fen: str, time_limit: float = 5.0, multipv: int = 3) -> list[dict]:
        """Run search lines using an available worker engine from the pool."""
        eng = await self._queue.get()
        try:
            return await eng.search_lines(fen, time_limit=time_limit, multipv=multipv)
        finally:
            self._queue.put_nowait(eng)

    async def fast_analyze(
        self,
        fen: str,
        depth: int = 20,
        multipv: int = 1,
        time_limit: float = 1.0,
    ) -> dict:
        """Run fast analyze using an available worker engine from the pool."""
        eng = await self._queue.get()
        try:
            return await eng.fast_analyze(fen, depth=depth, multipv=multipv, time_limit=time_limit)
        finally:
            self._queue.put_nowait(eng)
