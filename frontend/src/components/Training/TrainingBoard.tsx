import { useEffect, useRef, useState } from 'react';
import { Chessground } from 'chessground';
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';
import { Chess, Position } from 'chessops/chess';
import { parseFen, INITIAL_FEN } from 'chessops/fen';
import { chessgroundDests } from 'chessops/compat';
import { parseUci, parseSquare } from 'chessops/util';
import { makeSan } from 'chessops/san';
import type { Key } from 'chessground/types';

function posFromFen(fen: string): Position {
  try {
    return Chess.fromSetup(parseFen(fen).unwrap()).unwrap();
  } catch {
    return Chess.default();
  }
}

const PROMO_PIECES = [
  { role: 'queen', letter: 'q', white: '♕', black: '♛' },
  { role: 'rook', letter: 'r', white: '♖', black: '♜' },
  { role: 'bishop', letter: 'b', white: '♗', black: '♝' },
  { role: 'knight', letter: 'n', white: '♘', black: '♞' },
];

interface TrainingBoardProps {
  fen: string;
  lastMove?: [Key, Key];
  orientation?: 'white' | 'black';
  policy?: any[];
  saliency?: any;
  minefield?: any[];
  hotSquares?: string[];
  blunderFlash?: boolean;
  onMove?: (uci: string, san: string) => void;
  interactive?: boolean;
}

export default function TrainingBoard({
  fen,
  lastMove,
  orientation = 'white',
  policy = [],
  saliency = null,
  minefield = [],
  hotSquares = [],
  blunderFlash = false,
  onMove,
  interactive = true,
}: TrainingBoardProps) {
  const boardRef = useRef<HTMLDivElement>(null);
  const cgRef = useRef<ReturnType<typeof Chessground> | null>(null);

  // Pawn waiting on the last rank for the user to pick a promotion piece.
  // Chessground has no promotion dialog: it reports the drag as plain
  // orig+dest, so the piece choice has to be collected here before the
  // move (e.g. g2g1q) can be submitted.
  const [promo, setPromo] = useState<{ orig: Key; dest: Key } | null>(null);

  // The chessground move handler is registered once on mount, so it must
  // read the current fen/onMove through refs — capturing the props directly
  // would freeze it on the first drill's position and handler.
  const fenRef = useRef(fen);
  const onMoveRef = useRef(onMove);
  fenRef.current = fen;
  onMoveRef.current = onMove;

  const emitMove = (uci: string) => {
    const move = parseUci(uci);
    if (!move || !onMoveRef.current) return;
    let san = uci;
    try {
      san = makeSan(posFromFen(fenRef.current), move);
    } catch { /* keep uci as fallback */ }
    onMoveRef.current(uci, san);
  };
  const emitMoveRef = useRef(emitMove);
  emitMoveRef.current = emitMove;

  const syncBoard = () => {
    if (!cgRef.current) return;
    const pos = posFromFen(fen);
    cgRef.current.set({
      fen,
      lastMove,
      orientation,
      turnColor: pos.turn,
      movable: {
        color: interactive ? pos.turn : undefined,
        dests: interactive ? chessgroundDests(pos) : new Map(),
      }
    });
  };

  // Initialize board
  useEffect(() => {
    if (!boardRef.current) return;

    const pos = posFromFen(fen);

    const cg = Chessground(boardRef.current, {
      fen: pos ? fen : INITIAL_FEN,
      lastMove,
      orientation,
      // turnColor must always mirror the FEN: chessground only allows a
      // real drag when turnColor matches movable.color, and otherwise
      // silently captures the drag as a premove (piece moves on screen,
      // no move event fires). Premoves are meaningless in drills.
      turnColor: pos.turn,
      premovable: { enabled: false },
      movable: {
        free: false,
        color: interactive ? pos.turn : undefined,
        dests: interactive ? chessgroundDests(pos) : new Map(),
      },
    });

    cg.set({
      movable: {
        events: {
          after: (orig, dest) => {
            if (!onMoveRef.current) return;

            const oldPos = posFromFen(fenRef.current);
            const piece = oldPos.board.get(parseSquare(orig) ?? -1);
            if (piece?.role === 'pawn' && (dest[1] === '1' || dest[1] === '8')) {
              // Pawn reached the last rank: ask which piece before submitting.
              setPromo({ orig: orig as Key, dest: dest as Key });
              return;
            }

            emitMoveRef.current(orig + dest);
          }
        }
      }
    });

    cgRef.current = cg;

    return () => {
      cg.destroy();
      cgRef.current = null;
    };
  }, []);

  // Update FEN, orientation, and interactability
  useEffect(() => {
    syncBoard();
  }, [fen, lastMove, orientation, interactive]);

  const choosePromotion = (letter: string) => {
    if (!promo) return;
    const uci = promo.orig + promo.dest + letter;
    setPromo(null);
    emitMove(uci);
  };

  const cancelPromotion = () => {
    // Put the pawn back: chessground already shows it on the last rank.
    setPromo(null);
    syncBoard();
  };

  // Update overlays
  useEffect(() => {
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
    const markerPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    markerPath.setAttribute('d', 'M0,0 L0,4 L4,2 Z');
    markerPath.setAttribute('fill', 'rgba(0, 150, 255, 0.7)');
    marker.appendChild(markerPath);
    defs.appendChild(marker);

    const markerHot = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
    markerHot.setAttribute('id', 'arrowhead-hot');
    markerHot.setAttribute('markerWidth', '4');
    markerHot.setAttribute('markerHeight', '4');
    markerHot.setAttribute('refX', '2');
    markerHot.setAttribute('refY', '2');
    markerHot.setAttribute('orient', 'auto');
    const markerHotPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    markerHotPath.setAttribute('d', 'M0,0 L0,4 L4,2 Z');
    markerHotPath.setAttribute('fill', 'rgba(255, 50, 50, 0.8)');
    markerHot.appendChild(markerHotPath);
    defs.appendChild(markerHot);
    svg.appendChild(defs);

    const squareToCoords = (sq: string) => {
      const file = sq.charCodeAt(0) - 97; // a=0, h=7
      const rank = parseInt(sq[1], 10) - 1; // 1=0, 8=7
      const px = isBlack ? 7 - file : file;
      const py = isBlack ? rank : 7 - rank;
      return { x: px * 12.5 + 6.25, y: py * 12.5 + 6.25 };
    };

    if (blunderFlash) {
      const flashRect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
      flashRect.setAttribute('x', '0');
      flashRect.setAttribute('y', '0');
      flashRect.setAttribute('width', '100%');
      flashRect.setAttribute('height', '100%');
      flashRect.setAttribute('fill', 'rgba(255,0,0,0.3)');
      flashRect.style.animation = 'blunder-pulse 1s ease-out';
      svg.appendChild(flashRect);
    }

    if (saliency && Object.keys(saliency).length > 0) {
      for (const [sq, val] of Object.entries(saliency)) {
        if (typeof val !== 'number' || val < 0.05) continue;
        const { x, y } = squareToCoords(sq);
        const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        circle.setAttribute('cx', `${x}%`);
        circle.setAttribute('cy', `${y}%`);
        
        const isHot = hotSquares.includes(sq);
        const radius = isHot ? (val * 8 + 2) : (val * 5);
        circle.setAttribute('r', `${radius}%`);
        
        if (isHot) {
          circle.setAttribute('fill', `rgba(255, 60, 0, ${Math.min(val + 0.2, 0.8)})`);
          circle.setAttribute('stroke', 'rgba(255, 255, 0, 0.5)');
          circle.setAttribute('stroke-width', '0.5%');
        } else {
          circle.setAttribute('fill', `rgba(255, 200, 0, ${val * 0.6})`);
        }
        
        circle.style.mixBlendMode = 'screen';
        svg.appendChild(circle);
      }
    }

    if (minefield && minefield.length > 0) {
      let maxComp = Math.max(...minefield.map(m => m.complexity || 0));
      for (const move of minefield) {
        if (!move.uci) continue;
        const origSq = move.uci.slice(0, 2);
        const destSq = move.uci.slice(2, 4);
        const { x: x1, y: y1 } = squareToCoords(origSq);
        const { x: x2, y: y2 } = squareToCoords(destSq);

        const isBest = move.complexity === maxComp && move.complexity > 0;
        const comp = Math.max(0.1, move.complexity || 0.1);
        
        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', `${x1}%`);
        line.setAttribute('y1', `${y1}%`);
        line.setAttribute('x2', `${x2}%`);
        line.setAttribute('y2', `${y2}%`);
        
        const r = Math.floor(255);
        const g = Math.floor(150 * (1 - comp));
        line.setAttribute('stroke', `rgba(${r}, ${g}, 0, 0.8)`);
        line.setAttribute('stroke-width', `${Math.max(comp * 3, 0.5)}%`);
        line.setAttribute('marker-end', isBest ? 'url(#arrowhead-hot)' : 'url(#arrowhead)');
        
        if (isBest) {
          line.style.filter = 'drop-shadow(0 0 2px rgba(255,0,0,0.5))';
        }
        
        svg.appendChild(line);
      }
    } else if (policy && policy.length > 0) {
      let maxP = policy[0].p;
      for (const move of policy) {
        if (move.p < 0.05) continue; // Noise
        const origSq = move.uci.slice(0, 2);
        const destSq = move.uci.slice(2, 4);
        const { x: x1, y: y1 } = squareToCoords(origSq);
        const { x: x2, y: y2 } = squareToCoords(destSq);

        const isBest = move.p === maxP;

        const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        line.setAttribute('x1', `${x1}%`);
        line.setAttribute('y1', `${y1}%`);
        line.setAttribute('x2', `${x2}%`);
        line.setAttribute('y2', `${y2}%`);
        
        line.setAttribute('stroke', isBest ? 'rgba(255, 50, 50, 0.8)' : 'rgba(0, 150, 255, 0.7)');
        line.setAttribute('stroke-width', `${Math.max(move.p * 3, 0.5)}%`);
        line.setAttribute('marker-end', isBest ? 'url(#arrowhead-hot)' : 'url(#arrowhead)');
        
        if (isBest) {
          line.style.filter = 'drop-shadow(0 0 2px rgba(255,0,0,0.5))';
        }
        
        svg.appendChild(line);
      }
    }

  }, [fen, policy, saliency, minefield, hotSquares, blunderFlash]);

  const promoColor = promo?.dest[1] === '8' ? 'white' : 'black';
  const promoFile = promo ? promo.dest.charCodeAt(0) - 97 : 0;
  const promoX = orientation === 'black' ? 7 - promoFile : promoFile;
  // Promotion square as seen by the viewer: stack the picker from that
  // edge toward the middle of the board.
  const promoRank = promo ? parseInt(promo.dest[1], 10) - 1 : 0;
  const promoY = orientation === 'black' ? promoRank : 7 - promoRank;
  const promoDir = promoY <= 3 ? 1 : -1;

  return (
    <div style={{ width: '100%', maxWidth: '600px', margin: '0 auto', position: 'relative' }}>
      <div
        ref={boardRef}
        style={{ width: '100%', paddingBottom: '100%', position: 'relative' }}
      />
      {promo && (
        <div
          onClick={cancelPromotion}
          style={{
            position: 'absolute', inset: 0, zIndex: 100,
            background: 'rgba(0, 0, 0, 0.4)',
          }}
        >
          {PROMO_PIECES.map((p, i) => (
            <button
              key={p.role}
              onClick={(e) => { e.stopPropagation(); choosePromotion(p.letter); }}
              aria-label={`Promote to ${p.role}`}
              style={{
                position: 'absolute',
                left: `${promoX * 12.5}%`,
                top: `${(promoY + i * promoDir) * 12.5}%`,
                width: '12.5%', height: '12.5%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 'clamp(24px, 5.5vmin, 48px)', lineHeight: 1,
                color: promoColor === 'white' ? '#fff' : '#111',
                background: 'rgba(240, 217, 181, 0.95)',
                border: '1px solid rgba(0,0,0,0.4)', borderRadius: '6px',
                cursor: 'pointer', padding: 0,
                textShadow: promoColor === 'white'
                  ? '0 0 3px rgba(0,0,0,0.9)' : '0 0 3px rgba(255,255,255,0.6)',
              }}
            >
              {promoColor === 'white' ? p.white : p.black}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
