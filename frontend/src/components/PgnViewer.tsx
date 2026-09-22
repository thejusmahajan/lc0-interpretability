import { useState, useEffect, useRef, useReducer } from 'react';
import { Chessground } from 'chessground';
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import './PgnViewer.css';

// chessops
import { Chess, Position } from 'chessops/chess';
import { parseFen, INITIAL_FEN, makeFen } from 'chessops/fen';
import { chessgroundDests } from 'chessops/compat';
import { parseUci, makeUci } from 'chessops/util';
import { parsePgn } from 'chessops/pgn';
import { parseSan, makeSan } from 'chessops/san';
import { SteeringLinesPanel, type SteeringData } from './SteeringLinesPanel';

type ChessgroundApi = ReturnType<typeof Chessground>;

const DEFAULT_PGN = `[Event "?"]
[Site "?"]
[Date "????.??.??"]
[Round "?"]
[White "?"]
[Black "?"]
[Result "*"]

1. c4 c5 2. Nf3 e6 3. Nc3 Nc6 4. g3 Nf6 5. Bg2 Qb6 6. d3 Be7 7. e4 d6 8. O-O Bd7 9. a3 Ng4 10. Ne1 Nf6 11. Rb1 a5 12. f4 O-O 13. b3 Ne8 14. g4 Qd8 15. Nc2 Nc7 16. Kh1 Bf6 17. Ne2 e5 18. f5 Bg5 19. a4 h6 20. Bxg5 hxg5 21. Ne3 Nd4 22. Qd2 f6 23. Bf3 Kf7 24. h4 Rh8 25. h5 Bc6 *`;

type GameState = {
  fen: string;
  pos: Position;
  lastMoveUci: string | null;
  san: string | null;
  policy: any[];
  saliency: any;
  calcSaliency: any;
  evalObj: any;
  blunderFlash: boolean;
  steering?: SteeringData | null;
};

export default function PgnViewer() {
  const boardRef = useRef<HTMLDivElement>(null);
  const cgRef = useRef<ChessgroundApi | null>(null);

  const [pgnInput, setPgnInput] = useState(DEFAULT_PGN);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [autoAnalyze, setAutoAnalyze] = useState(true);
  const [showTop20, setShowTop20] = useState(false);
  const [thinkSeconds, setThinkSeconds] = useState(1); // LC0 time budget per analysis (seconds)
  const [glowMode, setGlowMode] = useState<'intuition' | 'calculation'>('intuition');
  const [calcLoading, setCalcLoading] = useState(false);
  const [previewLineUci, setPreviewLineUci] = useState<string | null>(null);

  // Linear game history. gameStates is a ref (mutated in place by async analysis);
  // currentIndexRef is the source of truth read by the (stable) chessground move
  // handler; currentIndex mirrors it for JSX. forceRender() re-renders on data updates.
  const gameStates = useRef<GameState[]>([]);
  const currentIndexRef = useRef(0);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [, forceRender] = useReducer((x) => x + 1, 0);
  const showTop20Ref = useRef(showTop20);
  showTop20Ref.current = showTop20;
  const thinkSecondsRef = useRef(thinkSeconds);
  thinkSecondsRef.current = thinkSeconds;
  const autoAnalyzeRef = useRef(autoAnalyze);
  autoAnalyzeRef.current = autoAnalyze;
  const analysisSeqRef = useRef(0);
  const debounceTimerRef = useRef<any>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Ref for the active move in the panel to enable auto-scrolling
  const activeMoveRef = useRef<HTMLSpanElement>(null);

  const currentState = gameStates.current[currentIndex];

  // ---- board + overlay sync helpers ---------------------------------------

  const syncBoard = (st: GameState) => {
    const cg = cgRef.current;
    if (!cg) return;
    const lastMove = st.lastMoveUci
      ? [st.lastMoveUci.substring(0, 2), st.lastMoveUci.substring(2, 4)]
      : undefined;
    cg.set({
      fen: st.fen,
      turnColor: st.pos.turn,
      movable: { free: false, color: 'both', dests: chessgroundDests(st.pos) },
      lastMove: lastMove as any,
    });
  };

  const paintOverlays = (st: GameState | undefined) => {
    if (!st) return;
    const policy = showTop20Ref.current ? st.policy : st.policy.slice(0, 5);
    const glow = glowMode === 'calculation' && st.calcSaliency ? st.calcSaliency : st.saliency;
    drawOverlays(glow, policy, st.blunderFlash);
  };

  useEffect(() => {
    paintOverlays(gameStates.current[currentIndexRef.current]);
  }, [glowMode]);

  // Move to a given index: sync the board, redraw overlays, analyze if needed.
  const goToIndex = (i: number) => {
    if (i < 0 || i >= gameStates.current.length) return;
    currentIndexRef.current = i;
    setCurrentIndex(i);
    const st = gameStates.current[i];
    syncBoard(st);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (autoAnalyzeRef.current && (!st.steering || (!st.saliency && st.policy.length === 0))) {
      drawOverlays(null, [], false); // clear stale overlays while analyzing
      debounceTimerRef.current = setTimeout(() => {
        analyzeFen(st.fen, st.lastMoveUci, i);
      }, 150);
    } else {
      paintOverlays(st);
      forceRender();
    }
  };

  // ---- user move (stable across renders; reads live state from refs) -------

  const handleMove = (orig: string, dest: string) => {
    const cur = gameStates.current[currentIndexRef.current];
    if (!cgRef.current || !cur) return;

    let uci = orig + dest;
    const probe = parseUci(uci);
    if (probe && 'from' in probe) {
      const piece = cur.pos.board.get(probe.from);
      const destRank = dest.charAt(1);
      if (piece && piece.role === 'pawn' && (destRank === '1' || destRank === '8')) {
        uci += 'q'; // auto-promote to queen (v1)
      }
    }

    const move = parseUci(uci);
    if (!move || !cur.pos.isLegal(move)) {
      syncBoard(cur); // illegal -> snap back
      return;
    }

    const newPos = cur.pos.clone();
    const san = makeSan(cur.pos, move);
    newPos.play(move);
    const newFen = makeFen(newPos.toSetup());

    const newState: GameState = {
      fen: newFen,
      pos: newPos,
      lastMoveUci: uci,
      san,
      policy: [],
      saliency: null,
      calcSaliency: null,
      evalObj: null,
      blunderFlash: false,
    };

    // Branch: drop any forward history, append, and advance.
    gameStates.current = gameStates.current.slice(0, currentIndexRef.current + 1);
    gameStates.current.push(newState);
    const newIndex = gameStates.current.length - 1;
    currentIndexRef.current = newIndex;
    setCurrentIndex(newIndex);

    syncBoard(newState);
    drawOverlays(null, [], false); // clear the previous position's arrows immediately
    setPreviewLineUci(null);
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
    }
    if (autoAnalyzeRef.current) {
      debounceTimerRef.current = setTimeout(() => {
        analyzeFen(newFen, uci, newIndex);
      }, 350);
    }
  };

  const handlePrev = () => goToIndex(currentIndexRef.current - 1);
  const handleNext = () => goToIndex(currentIndexRef.current + 1);

  const handleReset = () => {
    const pos = Chess.default();
    const startState: GameState = {
      fen: INITIAL_FEN,
      pos,
      lastMoveUci: null,
      san: null,
      policy: [],
      saliency: null,
      calcSaliency: null,
      evalObj: null,
      blunderFlash: false,
    };
    gameStates.current = [startState];
    currentIndexRef.current = 0;
    setCurrentIndex(0);
    syncBoard(startState);
    drawOverlays(null, [], false);
    setPreviewLineUci(null);
    if (autoAnalyzeRef.current) {
      analyzeFen(INITIAL_FEN, null, 0);
    }
  };

  // ---- analysis ------------------------------------------------------------

  const analyzeFen = async (
    fen: string,
    uciPlayed: string | null,
    stateIndex: number,
    timeOverride?: number,
  ) => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    const seq = ++analysisSeqRef.current;
    setIsAnalyzing(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: controller.signal,
        body: JSON.stringify({
          fen,
          multipv: 5,
          time_limit: timeOverride ?? thinkSecondsRef.current,
        }),
      });
      const data = await res.json();

      const policy = data.policy || [];
      const saliency = data.saliency || null;
      const evalObj = data.evaluation;

      let shouldFlash = false;
      if (uciPlayed && stateIndex > 0) {
        const prevPolicy = gameStates.current[stateIndex - 1]?.policy;
        if (prevPolicy && prevPolicy.length > 0) {
          const bestP = prevPolicy[0].p;
          const playedMove = prevPolicy.find((m: any) => m.uci === uciPlayed);
          const playedP = playedMove ? playedMove.p : 0;
          if (bestP - playedP > 0.25) shouldFlash = true;
        }
      }

      const targetState = gameStates.current[stateIndex];
      if (targetState && targetState.fen === fen) {
        targetState.policy = policy;
        targetState.saliency = saliency;
        targetState.evalObj = evalObj;
        targetState.blunderFlash = shouldFlash;
        targetState.steering = data.steering || null;

        // Only touch the board if this result is still for the visible position.
        if (stateIndex === currentIndexRef.current) {
          paintOverlays(targetState);
          forceRender(); // update eval readout
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        return; // Prior request was intentionally cancelled because a new move arrived
      }
      console.error('Analysis failed:', err);
    } finally {
      if (seq === analysisSeqRef.current) {
        setIsAnalyzing(false);
      }
    }
  };

  const computeCalcGlow = async () => {
    const st = gameStates.current[currentIndexRef.current];
    if (!st) return;
    setCalcLoading(true);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/calculation-glow', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ fen: st.fen, multipv: 3, time_limit: 5 }),
      });
      const data = await res.json();
      const target = gameStates.current[currentIndexRef.current];
      if (target && target.fen === st.fen) {
        target.calcSaliency = data.calculation_saliency || null;
        setGlowMode('calculation');
        paintOverlays(target);
        forceRender();
      }
    } catch (err) {
      console.error('Calculation glow failed:', err);
    } finally {
      setCalcLoading(false);
    }
  };

  // ---- PGN / FEN load -----------------------------------------------------

  const handleLoadPgn = () => {
    try {
      const trimmed = pgnInput.trim();

      // 1. Direct FEN check
      const fenRes = parseFen(trimmed);
      if (fenRes.isOk) {
        try {
          const setup = fenRes.unwrap();
          const startPos = Chess.fromSetup(setup).unwrap();
          const startFen = makeFen(startPos.toSetup());
          const states: GameState[] = [
            {
              fen: startFen,
              pos: startPos.clone(),
              lastMoveUci: null,
              san: null,
              policy: [],
              saliency: null,
              calcSaliency: null,
              evalObj: null,
              blunderFlash: false,
            },
          ];
          gameStates.current = states;
          currentIndexRef.current = 0;
          setCurrentIndex(0);
          syncBoard(states[0]);
          drawOverlays(null, [], false);
          analyzeFen(startFen, null, 0);
          return;
        } catch (e) {
          console.warn('Could not construct board from FEN:', e);
        }
      }

      // 2. Standard PGN parsing
      const games = parsePgn(pgnInput);
      if (games.length === 0) return;
      const game = games[0];

      let startFen = INITIAL_FEN;
      if (game.headers && game.headers.size > 0) {
        for (const [key, val] of game.headers.entries()) {
          if (key.toUpperCase() === 'FEN') startFen = val;
        }
      }

      let startPos: Position;
      try {
        startPos = Chess.fromSetup(parseFen(startFen).unwrap()).unwrap();
      } catch {
        startPos = Chess.default();
        startFen = INITIAL_FEN;
      }

      const states: GameState[] = [
        {
          fen: makeFen(startPos.toSetup()),
          pos: startPos.clone(),
          lastMoveUci: null,
          san: null,
          policy: [],
          saliency: null,
          calcSaliency: null,
          evalObj: null,
          blunderFlash: false,
        },
      ];

      let node = game.moves;
      let pos = startPos;
      while (node.children && node.children.length > 0) {
        const child = node.children[0];
        const move = parseSan(pos, child.data.san);
        if (!move) break;
        pos = pos.clone();
        const san = makeSan(pos, move);
        pos.play(move);
        states.push({
          fen: makeFen(pos.toSetup()),
          pos,
          lastMoveUci: makeUci(move),
          san,
          policy: [],
          saliency: null,
          calcSaliency: null,
          evalObj: null,
          blunderFlash: false,
        });
        node = child;
      }

      gameStates.current = states;
      currentIndexRef.current = 0;
      setCurrentIndex(0);
      syncBoard(states[0]);
      drawOverlays(null, [], false);
      if (autoAnalyze) {
        analyzeFen(states[0].fen, null, 0);
      }
    } catch (err) {
      console.error('Invalid PGN:', err);
    }
  };

  // ---- mount ---------------------------------------------------------------

  useEffect(() => {
    if (!boardRef.current) return;

    const pos = Chess.default();
    gameStates.current = [
      {
        fen: INITIAL_FEN,
        pos,
        lastMoveUci: null,
        san: null,
        policy: [],
        saliency: null,
        calcSaliency: null,
        evalObj: null,
        blunderFlash: false,
      },
    ];
    currentIndexRef.current = 0;
    setCurrentIndex(0);

    const cg = Chessground(boardRef.current, {
      fen: INITIAL_FEN,
      movable: {
        free: false,
        color: 'both',
        dests: chessgroundDests(pos),
        events: { after: handleMove }, // stable: reads live state via refs
      },
    });
    cgRef.current = cg;

    if (autoAnalyze) {
      analyzeFen(INITIAL_FEN, null, 0);
    }

    return () => {
      cg.destroy();
      cgRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    paintOverlays(gameStates.current[currentIndexRef.current]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showTop20]);

  // Auto-scroll the active move into view when currentIndex changes
  useEffect(() => {
    if (activeMoveRef.current) {
      activeMoveRef.current.scrollIntoView({ block: 'nearest' });
    }
  }, [currentIndex]);

  // ---- overlay rendering (direct SVG on the board) -------------------------

  const drawOverlays = (saliency: any, policy: any[], flash: boolean) => {
    if (!boardRef.current) return;
    const cgBoard = boardRef.current.querySelector('cg-board');
    if (!cgBoard) return;

    const isBlack = cgRef.current?.state.orientation === 'black';

    let svg = cgBoard.querySelector('.neural-overlay') as SVGSVGElement | null;
    if (!svg) {
      svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
      svg.classList.add('neural-overlay');
      svg.style.position = 'absolute';
      svg.style.top = '0';
      svg.style.left = '0';
      svg.style.width = '100%';
      svg.style.height = '100%';
      svg.style.pointerEvents = 'none';
      svg.style.zIndex = '50';
      cgBoard.appendChild(svg);
    }

    svg.innerHTML = '';

    const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
    const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    marker.setAttribute('id', 'arrowhead');
    marker.setAttribute('markerWidth', '4');
    marker.setAttribute('markerHeight', '4');
    marker.setAttribute('refX', '2');
    marker.setAttribute('refY', '2');
    marker.setAttribute('orient', 'auto');

    const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
    polygon.setAttribute('points', '0 0, 4 2, 0 4');
    polygon.setAttribute('fill', '#00ffcc');
    marker.appendChild(polygon);
    defs.appendChild(marker);
    svg.appendChild(defs);

    const getCoords = (sq: string) => {
      const file = sq.charCodeAt(0) - 97;
      const rank = sq.charCodeAt(1) - 49;
      const x = isBlack ? 7 - file : file;
      const y = isBlack ? rank : 7 - rank;
      return { x: (x + 0.5) * 12.5, y: (y + 0.5) * 12.5 };
    };

    if (saliency) {
      const color = flash ? '255, 0, 50' : '0, 150, 255';
      for (const [sq, val] of Object.entries(saliency)) {
        if ((val as number) > 0.05) {
          const coords = getCoords(sq);
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', coords.x + '%');
          circle.setAttribute('cy', coords.y + '%');
          circle.setAttribute('r', '6.25%');

          const gradId = 'glow-' + sq;
          const grad = document.createElementNS('http://www.w3.org/2000/svg', 'radialGradient');
          grad.setAttribute('id', gradId);
          grad.innerHTML = `
              <stop offset="0%" stop-color="rgba(${color}, ${(val as number) * 0.8})" />
              <stop offset="100%" stop-color="rgba(${color}, 0)" />
          `;
          defs.appendChild(grad);

          circle.setAttribute('fill', `url(#${gradId})`);
          svg.appendChild(circle);
        }
      }
    }

    if (policy && policy.length > 0) {
      const pMax = Math.max(...policy.map((m: any) => m.p ?? 0)) || 1;

      for (const move of policy) {
        const fromSq = move.from;
        const toSq = move.to;
        const p = move.p;
        if (!fromSq || !toSq || p < 0.01) continue;

        const ratio = Math.min(1, p / pMax);
        const width = 0.34 + ratio * 2.48; // Reduced by another 25%
        const opacity = 0.25 + ratio * 0.75;

        const fromCoords = getCoords(fromSq);
        const toCoords = getCoords(toSq);

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', fromCoords.x + '%');
        line.setAttribute('y1', fromCoords.y + '%');
        line.setAttribute('x2', toCoords.x + '%');
        line.setAttribute('y2', toCoords.y + '%');
        line.setAttribute('stroke', `rgba(0, 255, 204, ${opacity})`);
        line.setAttribute('stroke-width', width + '%');
        line.setAttribute('marker-end', 'url(#arrowhead)');
        svg.appendChild(line);

        // Numeric % labels only if top 20 is off to avoid clutter, or if ratio is very high
        if (!showTop20Ref.current && ratio >= 0.15) {
          const textX = fromCoords.x + (toCoords.x - fromCoords.x) * 0.7;
          const textY = fromCoords.y + (toCoords.y - fromCoords.y) * 0.7;
          
          const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
          text.setAttribute('x', textX + '%');
          text.setAttribute('y', textY + '%');
          text.setAttribute('fill', '#fff');
          text.setAttribute('font-size', '1.95%'); // Reduced by another 25%
          text.setAttribute('font-family', 'sans-serif');
          text.setAttribute('font-weight', 'bold');
          text.setAttribute('text-anchor', 'middle');
          text.setAttribute('alignment-baseline', 'middle');
          text.setAttribute('paint-order', 'stroke');
          text.setAttribute('stroke', '#000');
          text.setAttribute('stroke-width', '0.34%'); // Reduced by another 25%
          text.textContent = Math.round(p * 100) + '%';
          svg.appendChild(text);
        }
      }
    }
  };

  // ---- render --------------------------------------------------------------

  return (
    <div className="pgn-viewer-container">
      <div
        className="board-section glass-panel"
        style={{ padding: '20px', display: 'flex', flexDirection: 'column', alignItems: 'center' }}
      >
        <div ref={boardRef} style={{ width: '500px', height: '500px' }} className="cg-board-wrap" />

        <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
          <button className="load-btn" onClick={handleReset}>
            New Game
          </button>
          <button className="load-btn" onClick={handlePrev} disabled={currentIndex === 0}>
            Take-back / Prev
          </button>
          <button
            className="load-btn"
            onClick={handleNext}
            disabled={currentIndex >= gameStates.current.length - 1}
          >
            Next
          </button>
        </div>
      </div>

      <div className="input-section glass-panel">
        <h2>Neural Vision</h2>

        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
            <input type="checkbox" checked={autoAnalyze} onChange={(e) => setAutoAnalyze(e.target.checked)} />
            Auto-Analyze on Move
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
            <input type="checkbox" checked={showTop20} onChange={(e) => setShowTop20(e.target.checked)} />
            Show Top 20 Arrows
          </label>

          {isAnalyzing && <span style={{ color: '#00ffcc', fontSize: '14px' }}>Analyzing...</span>}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            Thinking time:
            <select
              value={thinkSeconds}
              onChange={(e) => setThinkSeconds(Number(e.target.value))}
              style={{ padding: '4px', borderRadius: '4px' }}
            >
              <option value={1}>1s (Fast)</option>
              <option value={2}>2s (Normal)</option>
              <option value={5}>5s (Deep)</option>
              <option value={15}>15s (Very Deep)</option>
            </select>
          </label>

          <button
            className="load-btn"
            disabled={isAnalyzing || !currentState}
            onClick={() => {
              const st = gameStates.current[currentIndexRef.current];
              if (st) analyzeFen(st.fen, st.lastMoveUci, currentIndexRef.current, 15);
            }}
          >
            Think Deeper ⏱
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '15px' }}>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input type="radio" checked={glowMode === 'intuition'} onChange={() => setGlowMode('intuition')} />
            Intuition Glow
          </label>
          <label style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input type="radio" checked={glowMode === 'calculation'} onChange={() => setGlowMode('calculation')} />
            Calculation Glow
          </label>
          <button className="load-btn" disabled={calcLoading} onClick={computeCalcGlow}>
            {calcLoading ? 'Calculating…' : 'Compute (~15s)'}
          </button>
        </div>

        {currentState?.evalObj && (
          <div style={{ marginBottom: '15px', padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '6px' }}>
            <strong>Evaluation: </strong>
            <span style={{ color: currentState.evalObj.value > 0 ? '#00ffcc' : '#ff3366', fontWeight: 'bold' }}>
              {currentState.evalObj.type === 'mate'
                ? `M${currentState.evalObj.value}`
                : (currentState.evalObj.value / 100).toFixed(2)}
            </span>
          </div>
        )}

        <SteeringLinesPanel
          steering={currentState?.steering}
          activeUci={previewLineUci}
          isAnalyzing={isAnalyzing}
          onPreviewLine={(_pv, uci) => {
            setPreviewLineUci(uci);
            if (cgRef.current && uci.length >= 4) {
              const orig = uci.substring(0, 2) as any;
              const dest = uci.substring(2, 4) as any;
              cgRef.current.set({
                drawable: {
                  shapes: [
                    { orig, dest, brush: 'yellow' }
                  ]
                }
              });
            }
          }}
          onPlayMove={(uci) => {
            if (uci.length >= 4) {
              handleMove(uci.substring(0, 2), uci.substring(2, 4));
            }
          }}
        />

        <textarea
          value={pgnInput}
          onChange={(e) => setPgnInput(e.target.value)}
          placeholder="Paste PGN or FEN here..."
          style={{ height: '140px' }}
        />

        <button className="load-btn" onClick={handleLoadPgn}>
          Load PGN / FEN
        </button>

        <div className="move-list-panel">
          {(() => {
            const moves = [];
            // Skip the start state (index 0)
            for (let i = 1; i < gameStates.current.length; i += 2) {
              const moveNum = Math.ceil(i / 2);
              const wState = gameStates.current[i];
              const bState = i + 1 < gameStates.current.length ? gameStates.current[i + 1] : null;

              moves.push(
                <div key={i} className="move-row">
                  <span className="move-number">{moveNum}.</span>
                  <span
                    className={`move-san ${currentIndex === i ? 'active-move' : ''}`}
                    onClick={() => goToIndex(i)}
                    ref={currentIndex === i ? activeMoveRef : null}
                  >
                    {wState.san}
                  </span>
                  {bState ? (
                    <span
                      className={`move-san ${currentIndex === i + 1 ? 'active-move' : ''}`}
                      onClick={() => goToIndex(i + 1)}
                      ref={currentIndex === i + 1 ? activeMoveRef : null}
                    >
                      {bState.san}
                    </span>
                  ) : (
                    <span className="move-san empty"></span>
                  )}
                </div>
              );
            }
            return moves;
          })()}
        </div>

        {currentState?.fen && (
          <div style={{ marginTop: '15px', fontSize: '12px', color: '#ccc', wordBreak: 'break-all' }}>
            <strong>Current FEN:</strong> {currentState.fen}
          </div>
        )}
      </div>
    </div>
  );
}
