import { useState, useEffect, useMemo } from 'react';
import { listRepertoires, buildRepertoire, getRepertoireTree, getTopOpenings } from '../../api/training';
import TrainingBoard from './TrainingBoard';
import { Chess } from 'chessops/chess';
import { parseFen, makeFen } from 'chessops/fen';
import { parseSan, makeSan } from 'chessops/san';
import { makeUci, parseUci } from 'chessops/util';
import type { Key } from 'chessground/types';
import './Training.css';

type Style = 'weakness' | 'sacrificial';
type Color = 'white' | 'black';

const VARIANTS: { style: Style; color: Color; label: string }[] = [
  { style: 'weakness', color: 'white', label: 'Weakness · White' },
  { style: 'weakness', color: 'black', label: 'Weakness · Black' },
  { style: 'sacrificial', color: 'white', label: 'Sacrificial · White' },
  { style: 'sacrificial', color: 'black', label: 'Sacrificial · Black' },
];

function variantKey(style: string, color: string) {
  return `${style}_${color}`;
}

// Replay the SAN line (e.g. "1. e4 e5 2. d4") to its tabiya for a board preview.
function lineToPosition(linePgn: string): { fen: string; lastMove?: [Key, Key] } {
  const tokens = (linePgn || '').replace(/\d+\./g, '').trim().split(/\s+/).filter(Boolean);
  const pos = Chess.default();
  let lastUci: string | undefined;
  for (const san of tokens) {
    const move = parseSan(pos, san);
    if (!move) break;
    lastUci = makeUci(move);
    pos.play(move);
  }
  return {
    fen: makeFen(pos.toSetup()),
    lastMove: lastUci
      ? [lastUci.slice(0, 2) as Key, lastUci.slice(2, 4) as Key]
      : undefined,
  };
}

function normCastling(uci: string): string {
  if (uci === 'e1h1') return 'e1g1';
  if (uci === 'e1a1') return 'e1c1';
  if (uci === 'e8h8') return 'e8g8';
  if (uci === 'e8a8') return 'e8c8';
  return uci;
}

function normFen(fen: string): string {
  return fen.trim().split(/\s+/).slice(0, 3).join(' ');
}

function applyUciMove(fen: string, uci: string): { fen: string; lastMove?: [Key, Key]; moveSan?: string } {
  try {
    const pos = Chess.fromSetup(parseFen(fen).unwrap()).unwrap();
    const move = parseUci(uci);
    if (!move) return { fen };
    let moveSan = uci;
    try {
      moveSan = makeSan(pos, move);
    } catch { /* fallback to uci */ }
    pos.play(move);
    const newFen = makeFen(pos.toSetup());
    return {
      fen: newFen,
      lastMove: [uci.slice(0, 2) as Key, uci.slice(2, 4) as Key],
      moveSan,
    };
  } catch {
    return { fen };
  }
}

interface RepertoireTrainerProps {
  eco: string;
  color: Color;
  openingName: string;
  onSelectMode?: (mode: 'recommendations' | 'train') => void;
}

function RepertoireTrainer({ eco, color, openingName, onSelectMode }: RepertoireTrainerProps) {
  const [tree, setTree] = useState<any>(null);
  const [treeLoading, setTreeLoading] = useState(true);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [currentNodeId, setCurrentNodeId] = useState<string | null>(null);
  const [activeFen, setActiveFen] = useState<string>('');
  const [activeLastMove, setActiveLastMove] = useState<[Key, Key] | undefined>();
  const [userError, setUserError] = useState<string | null>(null);
  const [userSuccess, setUserSuccess] = useState<string | null>(null);
  const [isAnimating, setIsAnimating] = useState(false);
  const [completedBranch, setCompletedBranch] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const [replyIndex, setReplyIndex] = useState<number>(0);

  useEffect(() => {
    let isMounted = true;
    const timeoutId = setTimeout(() => {
      if (isMounted) {
        setTreeError('Tree build timed out after 120s. Engine analysis takes longer for un-cached lines; please try again.');
        setTreeLoading(false);
      }
    }, 120000);

    async function loadTree() {
      try {
        setTreeLoading(true);
        setTreeError(null);
        const data = await getRepertoireTree(eco, color);
        if (!isMounted) return;
        clearTimeout(timeoutId);
        setTree(data);
        if (data && data.nodes && data.nodes.length > 0) {
          const root = data.nodes[0];
          setCurrentNodeId(root.id);
          setActiveFen(root.fen_before);
          setActiveLastMove(undefined);
          setUserError(null);
          setUserSuccess(null);
          setCompletedBranch(false);
          setHistory([]);
          setReplyIndex(0);
        }
        setTreeLoading(false);
      } catch (err: any) {
        if (!isMounted) return;
        clearTimeout(timeoutId);
        setTreeError(err.message || 'Failed to load tree');
        setTreeLoading(false);
      }
    }
    loadTree();
    return () => {
      isMounted = false;
      clearTimeout(timeoutId);
    };
  }, [eco, color]);

  const nodeMap = useMemo(() => {
    const map = new Map<string, any>();
    if (tree && tree.nodes) {
      for (const n of tree.nodes) {
        map.set(n.id, n);
      }
    }
    return map;
  }, [tree]);

  const currentNode = currentNodeId ? nodeMap.get(currentNodeId) : null;

  // Check for degenerate / un-trainable trees (e.g. 0 nodes, single root without user_move, or no user_moves anywhere)
  const isDegenerateTree = useMemo(() => {
    if (!tree || !tree.nodes || tree.nodes.length === 0) return true;
    if (tree.nodes.length === 1 && tree.nodes[0].is_user_node && !tree.nodes[0].user_move) return true;
    const hasAnyUserMove = tree.nodes.some((n: any) => n.is_user_node && Boolean(n.user_move));
    return !hasAnyUserMove;
  }, [tree]);

  // Handle opponent turn at current node (e.g. root node for Black or after branching)
  useEffect(() => {
    if (isDegenerateTree || !currentNode || currentNode.is_user_node || isAnimating || completedBranch) return;

    const replies = currentNode.opponent_replies || [];
    if (replies.length === 0) {
      setCompletedBranch(true);
      return;
    }

    const chosenReply = replies[replyIndex % replies.length];
    const afterReply = applyUciMove(currentNode.fen_before, chosenReply.uci);

    // Find child node
    const matchingChild = tree.nodes.find(
      (n: any) => normFen(n.fen_before) === normFen(afterReply.fen)
    );

    setIsAnimating(true);
    const animDelay = typeof window !== 'undefined' && (window as any).IS_TEST_ENV ? 10 : 450;
    const timer = setTimeout(() => {
      setActiveFen(afterReply.fen);
      setActiveLastMove(afterReply.lastMove);
      if (chosenReply.san) {
        setHistory(h => [...h, chosenReply.san]);
      }
      if (matchingChild) {
        setCurrentNodeId(matchingChild.id);
      } else {
        setCompletedBranch(true);
      }
      setIsAnimating(false);
    }, animDelay);

    return () => clearTimeout(timer);
  }, [currentNode, replyIndex, isAnimating, completedBranch, tree, isDegenerateTree]);

  if (treeLoading) {
    return (
      <div className="glass-panel" style={{ padding: '2.5rem', textAlign: 'center' }}>
        <div
          className="spinner"
          style={{
            margin: '0 auto 1rem auto',
            width: '36px',
            height: '36px',
            border: '3px solid rgba(56, 189, 248, 0.2)',
            borderTopColor: '#38bdf8',
            borderRadius: '50%',
          }}
        />
        <h3 className="gradient-text" style={{ margin: '0 0 0.5rem 0' }}>Building / Loading Variation Tree...</h3>
        <p className="subtle" style={{ maxWidth: '500px', margin: '0 auto' }}>
          Evaluating position nodes with LC0 engine for <strong>{openingName}</strong> ({eco}). This can take up to a minute for un-cached openings...
        </p>
      </div>
    );
  }

  if (treeError) {
    return (
      <div className="glass-panel error-msg" style={{ padding: '1.5rem', textAlign: 'center' }}>
        <p style={{ margin: '0 0 1rem 0' }}>{treeError}</p>
        <button className="glass-btn primary" onClick={() => onSelectMode?.('recommendations')}>
          Back to Recommendations
        </button>
      </div>
    );
  }

  if (isDegenerateTree) {
    return (
      <div className="glass-panel" style={{ padding: '2.5rem', textAlign: 'center' }}>
        <h3 className="gradient-text" style={{ margin: '0 0 0.5rem 0' }}>No Trainable Variation Tree</h3>
        <p className="subtle" style={{ maxWidth: '520px', margin: '0 auto 1.5rem auto', lineHeight: 1.5 }}>
          No variation tree could be built for <strong>{openingName}</strong> ({eco}) — too few of your games reach this line.
        </p>
        <button className="glass-btn primary" onClick={() => onSelectMode?.('recommendations')}>
          Back to Recommendations
        </button>
      </div>
    );
  }

  const isInteractive = Boolean(
    !isAnimating &&
    !completedBranch &&
    currentNode?.is_user_node &&
    currentNode?.user_move
  );

  const handleUserMove = (uci: string, san: string) => {
    if (!isInteractive || !currentNode || !currentNode.is_user_node || !currentNode.user_move) return;

    const targetUci = currentNode.user_move.uci;
    const isCorrect = normCastling(uci) === normCastling(targetUci);

    if (!isCorrect) {
      setUserSuccess(null);
      setUserError(`Wrong move! Correct move is ${currentNode.user_move.san} (${targetUci}). Try again!`);
      return;
    }

    setUserError(null);
    setUserSuccess(`Correct! Played ${san || currentNode.user_move.san}`);

    // Play user move
    const afterUser = applyUciMove(activeFen, currentNode.user_move.uci);
    const moveSan = san || currentNode.user_move.san;

    const replies = currentNode.opponent_replies || [];
    if (replies.length === 0) {
      setActiveFen(afterUser.fen);
      setActiveLastMove(afterUser.lastMove);
      setHistory(h => [...h, moveSan]);
      setCompletedBranch(true);
      return;
    }

    const chosenReply = replies[replyIndex % replies.length];
    const afterReply = applyUciMove(afterUser.fen, chosenReply.uci);

    const matchingChild = tree.nodes.find(
      (n: any) => normFen(n.fen_before) === normFen(afterReply.fen)
    );

    setActiveFen(afterUser.fen);
    setActiveLastMove(afterUser.lastMove);
    setHistory(h => [...h, moveSan]);
    setIsAnimating(true);

    const animDelay = typeof window !== 'undefined' && (window as any).IS_TEST_ENV ? 10 : 500;
    setTimeout(() => {
      setActiveFen(afterReply.fen);
      setActiveLastMove(afterReply.lastMove);
      if (chosenReply.san) {
        setHistory(h => [...h, chosenReply.san]);
      }
      if (matchingChild) {
        setCurrentNodeId(matchingChild.id);
      } else {
        setCompletedBranch(true);
      }
      setIsAnimating(false);
    }, animDelay);
  };

  const resetWalk = () => {
    if (tree && tree.nodes && tree.nodes.length > 0) {
      const root = tree.nodes[0];
      setCurrentNodeId(root.id);
      setActiveFen(root.fen_before);
      setActiveLastMove(undefined);
      setUserError(null);
      setUserSuccess(null);
      setCompletedBranch(false);
      setHistory([]);
    }
  };

  const reRollLine = () => {
    setReplyIndex(prev => prev + 1);
    resetWalk();
  };

  const availableReplies = currentNode?.opponent_replies || [];

  return (
    <div className="repertoire-trainer-layout" style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 1.2fr) minmax(280px, 1fr)', gap: '1.5rem' }}>
      <div className="board-section glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
          <h3 style={{ margin: 0 }}>{openingName} ({eco})</h3>
          <span className="tag" style={{ textTransform: 'capitalize' }}>{color} view</span>
        </div>
        <TrainingBoard
          fen={activeFen}
          lastMove={activeLastMove}
          orientation={color}
          interactive={isInteractive}
          onMove={handleUserMove}
          blunderFlash={Boolean(userError)}
        />
        {history.length > 0 && (
          <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: '#94a3b8', wordBreak: 'break-word' }}>
            <strong>Walked line:</strong> {history.join(' ')}
          </div>
        )}
      </div>

      <div className="trainer-controls glass-panel" style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        <div>
          <h3 className="gradient-text" style={{ margin: '0 0 0.5rem 0' }}>Repertoire Walk</h3>
          <p className="subtle" style={{ margin: 0 }}>
            {completedBranch
              ? 'Branch complete!'
              : currentNode?.is_user_node
              ? 'Your turn: find the correct repertoire move.'
              : 'Facing opponent response...'}
          </p>
        </div>

        {/* Expected Move & Branch Line Overview */}
        <div className="glass-card" style={{ borderLeft: '3px solid #38bdf8' }}>
          <div style={{ fontSize: '0.85rem', fontWeight: 600, color: '#38bdf8', marginBottom: '0.25rem' }}>
            Expected Repertoire Move:
            <span style={{ color: '#fff', fontSize: '1rem', marginLeft: '0.5rem' }}>
              {currentNode?.user_move?.san || (completedBranch ? 'Branch complete' : 'Opponent turn')}
            </span>
          </div>
          <div style={{ fontSize: '0.8rem', color: '#94a3b8' }}>
            {currentNode?.is_user_node && currentNode?.user_move
              ? `Play ${currentNode.user_move.san} on the board.`
              : completedBranch
              ? 'You reached the end of this variation branch.'
              : 'Facing opponent reply...'}
          </div>
        </div>

        {/* Node status & Critical Badge */}
        <div className="glass-card" style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Ply {currentNode?.ply ?? 0} / Depth {tree?.depth}</span>
            {currentNode?.critical && (
              <span className="severity blunder" style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171', fontWeight: 600, padding: '2px 8px', borderRadius: '4px' }}>
                ⚡ CRITICAL NODE ({currentNode.critical_reason})
              </span>
            )}
          </div>

          <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            {currentNode?.eval_cp != null && (
              <span><strong>Eval:</strong> {currentNode.eval_cp >= 0 ? `+${(currentNode.eval_cp / 100).toFixed(2)}` : (currentNode.eval_cp / 100).toFixed(2)}</span>
            )}
            {currentNode?.complexity != null && (
              <span><strong>Complexity:</strong> {currentNode.complexity.toFixed(2)}</span>
            )}
            {currentNode?.user_blind_rate != null && (
              <span><strong>Blind Rate:</strong> {(currentNode.user_blind_rate * 100).toFixed(0)}%</span>
            )}
          </div>
        </div>

        {/* Feedback notices */}
        {userError && (
          <div className="error-msg" style={{ margin: 0 }}>
            {userError}
          </div>
        )}
        {userSuccess && !userError && (
          <div style={{ color: '#34d399', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)', padding: '0.75rem', borderRadius: '8px' }}>
            {userSuccess}
          </div>
        )}

        {/* Opponent reply branch selection / re-roll */}
        {availableReplies.length > 0 && (
          <div className="glass-card">
            <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.5rem', color: '#94a3b8' }}>
              Opponent replies at this branch ({availableReplies.length}):
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
              {availableReplies.map((r: any, idx: number) => (
                <button
                  key={r.uci + idx}
                  className={`glass-btn ${(replyIndex % availableReplies.length) === idx ? 'active' : ''}`}
                  style={{ fontSize: '0.8rem', padding: '0.3rem 0.6rem' }}
                  disabled={isAnimating}
                  onClick={() => setReplyIndex(idx)}
                >
                  {r.san} ({(r.pct * 100).toFixed(0)}%)
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Coach Explanation Panel (Placeholder for R3 / Node Explanation) */}
        <div className="glass-card" style={{ borderLeft: '3px solid #38bdf8' }}>
          <h4 style={{ margin: '0 0 0.5rem 0', color: '#38bdf8', fontSize: '0.9rem' }}>Coach Explanation</h4>
          {/* Derived from LC0's own computed values only. The generated-prose
              branch that used to sit here was removed 2026-08-30: it rendered
              text written by a language model that had been handed a FEN and an
              eval and nothing else. See backend/tests/test_llm_seam.py. */}
          <p style={{ margin: 0, fontSize: '0.85rem', color: 'rgba(255,255,255,0.7)', lineHeight: 1.4 }}>
            <em>
              {currentNode?.critical
                ? `Critical node due to ${currentNode.critical_reason}. `
                : 'Standard repertoire node. '}
              Best move: <strong>{currentNode?.user_move?.san || 'N/A'}</strong> ({currentNode?.eval_cp != null ? `${(currentNode.eval_cp / 100).toFixed(2)}cp` : 'N/A'}).
            </em>
          </p>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', gap: '0.75rem', marginTop: 'auto' }}>
          <button className="glass-btn primary" style={{ flex: 1 }} disabled={isAnimating} onClick={reRollLine}>
            Walk Another Line
          </button>
          <button className="glass-btn" disabled={isAnimating || history.length === 0} onClick={resetWalk}>
            Reset Line
          </button>
        </div>
      </div>
    </div>
  );
}

export default function RepertoirePanel() {
  const [reps, setReps] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [selectedRec, setSelectedRec] = useState(0);
  const [buildingKey, setBuildingKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<'recommendations' | 'train'>('recommendations');
  const [trainColor, setTrainColor] = useState<Color>('white');
  const [topOpenings, setTopOpenings] = useState<any[]>([]);
  const [selectedEco, setSelectedEco] = useState<string>('A40');

  const load = async () => {
    try {
      setLoading(true);
      const list = await listRepertoires();
      setReps(list);
      if (list.length > 0 && !selectedKey) {
        setSelectedKey(variantKey(list[0].style, list[0].color));
      }
      setLoading(false);
    } catch (e: any) {
      setError(e.message || 'Failed to load repertoires');
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    getTopOpenings(12)
      .then((res: any) => {
        const whiteOps = (res?.white || []).map((o: any) => ({ ...o, color: 'white' }));
        const blackOps = (res?.black || []).map((o: any) => ({ ...o, color: 'black' }));
        setTopOpenings([...whiteOps, ...blackOps]);
      })
      .catch(() => { /* selector fallback */ });
  }, []);

  useEffect(() => {
    if (mode === 'train' && topOpenings.length > 0) {
      const colorAvailable = topOpenings.filter((o: any) => o.color === trainColor);
      if (colorAvailable.length > 0 && !colorAvailable.some((o: any) => o.eco === selectedEco)) {
        setSelectedEco(colorAvailable[0].eco);
      }
    }
  }, [trainColor, topOpenings, mode]);

  const colorOpenings = useMemo(
    () => topOpenings.filter((o: any) => !o.color || o.color === trainColor),
    [topOpenings, trainColor]
  );

  const byKey = useMemo(() => {
    const m: Record<string, any> = {};
    for (const r of reps) m[variantKey(r.style, r.color)] = r;
    return m;
  }, [reps]);

  const selected = selectedKey ? byKey[selectedKey] : null;
  const recs = selected?.recommendations || [];
  const rec = recs[selectedRec];

  const preview = useMemo(
    () => (rec ? lineToPosition(rec.line_pgn) : null),
    [rec]
  );

  const handleBuild = async (style: Style, color: Color) => {
    const key = variantKey(style, color);
    try {
      setBuildingKey(key);
      setError(null);
      await buildRepertoire(color, style);
      await load();
      setSelectedKey(key);
      setSelectedRec(0);
    } catch (e: any) {
      setError(e.message || 'Build failed (is a profile diagnosed?)');
    } finally {
      setBuildingKey(null);
    }
  };

  const selectVariant = (key: string) => {
    setSelectedKey(key);
    setSelectedRec(0);
  };

  const activeEco = selectedEco || rec?.eco || 'A40';
  const activeColor = trainColor || selected?.color || 'white';
  const activeOpeningName = recs.find((r: any) => r.eco === activeEco)?.name || topOpenings.find((o: any) => o.eco === activeEco)?.name || 'Queen\'s Pawn';

  if (loading) return <div className="glass-panel">Loading repertoires...</div>;

  return (
    <div className="repertoire-panel">
      <div className="glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '0.5rem' }}>
          <h2 className="gradient-text" style={{ margin: 0 }}>Opening Repertoire</h2>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className={`glass-btn ${mode === 'recommendations' ? 'active' : ''}`}
              onClick={() => setMode('recommendations')}
            >
              Recommendations
            </button>
            <button
              className={`glass-btn ${mode === 'train' ? 'active' : ''}`}
              onClick={() => setMode('train')}
            >
              Train Repertoire
            </button>
          </div>
        </div>

        <p className="subtle">
          Sharp, engine-sound openings whose middlegames force the tactics you
          miss most. Four variants: a weakness-targeting and a sacrificial line
          set for each color.
        </p>
        <div className="variant-grid">
          {VARIANTS.map(v => {
            const key = variantKey(v.style, v.color);
            const built = byKey[key];
            const isBuilding = buildingKey === key;
            return (
              <div
                key={key}
                className={`variant-card ${selectedKey === key ? 'active' : ''} ${built ? '' : 'empty'}`}
                onClick={() => built && selectVariant(key)}
              >
                <div className="variant-label">{v.label}</div>
                {built ? (
                  <div className="variant-meta">
                    {built.recommendations?.length || 0} lines
                  </div>
                ) : (
                  <button
                    className="glass-btn"
                    disabled={isBuilding}
                    onClick={(e) => { e.stopPropagation(); handleBuild(v.style, v.color); }}
                  >
                    {isBuilding ? 'Building…' : 'Build'}
                  </button>
                )}
              </div>
            );
          })}
        </div>
        {error && <div className="error-msg" style={{ marginTop: '10px' }}>{error}</div>}
      </div>

      {mode === 'recommendations' && selected && recs.length > 0 && (
        <div className="repertoire-detail">
          <div className="rec-list glass-panel">
            <h3>Recommended lines</h3>
            {recs.map((r: any, i: number) => (
              <div
                key={r.tag + i}
                className={`rec-item ${i === selectedRec ? 'active' : ''}`}
                onClick={() => setSelectedRec(i)}
              >
                <div className="rec-name">{r.name}</div>
                <div className="rec-sub">
                  <span className="tag">{r.eco}</span>
                  <span className="rec-line">{r.line_pgn}</span>
                </div>
                <div className="rec-stats">
                  <span title="LC0 eval of the tabiya (mover POV)">
                    eval {(r.eval_cp / 100).toFixed(2)}
                  </span>
                  {r.draw_pct != null && <span title="WDL draw share">draw {r.draw_pct}%</span>}
                  <span className="tag hot">{r.primary_motif}</span>
                </div>
              </div>
            ))}
          </div>

          {rec && (
            <div className="rec-board glass-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                <h3 style={{ margin: 0 }}>{rec.name}</h3>
                <button
                  className="glass-btn primary"
                  style={{ fontSize: '0.85rem', padding: '0.4rem 0.8rem' }}
                  onClick={() => {
                    setSelectedEco(rec.eco);
                    setTrainColor(selected.color);
                    setMode('train');
                  }}
                >
                  Train this line
                </button>
              </div>
              {preview && (
                <TrainingBoard
                  fen={preview.fen}
                  lastMove={preview.lastMove}
                  orientation={selected.color}
                  interactive={false}
                />
              )}
              <p className="rec-rationale">{rec.rationale}</p>
            </div>
          )}
        </div>
      )}

      {mode === 'train' && (
        <>
          <div className="glass-panel" style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap', marginBottom: '1rem' }}>
            <span style={{ fontWeight: 600 }}>Train opening:</span>
            <div style={{ display: 'flex', gap: '0.25rem' }}>
              <button
                className={`glass-btn ${activeColor === 'white' ? 'active' : ''}`}
                style={{ textTransform: 'capitalize' }}
                onClick={() => setTrainColor('white')}
              >
                white
              </button>
              <button
                className={`glass-btn ${activeColor === 'black' ? 'active' : ''}`}
                style={{ textTransform: 'capitalize' }}
                onClick={() => setTrainColor('black')}
              >
                black
              </button>
            </div>

            <select
              className="glass-input"
              value={activeEco}
              onChange={(e) => setSelectedEco(e.target.value)}
              style={{ minWidth: '280px' }}
            >
              {colorOpenings.length > 0 ? (
                colorOpenings.map((o: any) => (
                  <option key={`${o.color}-${o.eco}`} value={o.eco}>
                    {o.eco} - {o.name} ({o.n_games || o.count || 0} games)
                  </option>
                ))
              ) : (
                <option value={activeEco}>{activeEco}</option>
              )}
            </select>
          </div>

          <RepertoireTrainer
            eco={activeEco}
            color={activeColor}
            openingName={activeOpeningName}
            onSelectMode={setMode}
          />
        </>
      )}

      {selected && recs.length === 0 && mode === 'recommendations' && (
        <div className="glass-panel">
          No sound lines passed the soundness/sharpness gate for this variant.
        </div>
      )}
    </div>
  );
}
