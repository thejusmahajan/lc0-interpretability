"""
UCI Engine Wrapper for Stockfish.
Used strictly as a baseline opponent to evaluate LC0's tactical configurations.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import chess
import chess.engine

logger = logging.getLogger(__name__)

ENGINE_DIR = Path(r"C:\Users\Admin\Documents\chess_speak_out_loud\engine")
STOCKFISH_EXE = ENGINE_DIR / "stockfish" / "stockfish-windows-x86-64.exe"

class StockfishEngine:
    """Wrapper around the Stockfish UCI chess engine."""

    def __init__(self, engine_path: Optional[str] = None) -> None:
        self.engine_path: Path = Path(engine_path) if engine_path else STOCKFISH_EXE
        self.engine: Optional[chess.engine.SimpleEngine] = None
        self._lock: asyncio.Lock = asyncio.Lock()

    async def start(self) -> None:
        if not self.engine_path.exists():
            logger.error("Stockfish binary not found at %s", self.engine_path)
            return

        try:
            transport, engine = await chess.engine.popen_uci(str(self.engine_path))
            
            # Stockfish optimizations for fast tactical play
            await engine.configure({"Threads": 2, "Hash": 128})
            
            self.engine = engine
            logger.info("Stockfish engine started successfully from %s", self.engine_path)
        except Exception as exc:
            logger.error("Failed to start Stockfish: %s", exc)
            self.engine = None

    async def stop(self) -> None:
        if self.engine is not None:
            try:
                await self.engine.quit()
                logger.info("Stockfish stopped.")
            except Exception as exc:
                logger.warning("Error while stopping Stockfish: %s", exc)
            finally:
                self.engine = None

    async def play(self, board: chess.Board, time_limit: float = 0.5) -> chess.Move:
        """Play a move using Stockfish."""
        if self.engine is None:
            raise RuntimeError("Stockfish is not running")

        async with self._lock:
            result = await self.engine.play(board, chess.engine.Limit(time=time_limit))
            return result.move
