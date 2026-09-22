import { useState, useEffect } from 'react';
import TrainingBoard from './TrainingBoard';
import {
  startSacSession,
  submitSacGuess,
  getSacStats,
  startSacPlayout,
  submitPlayoutMove,
} from '../../api/training';
import type {
  SacPosition,
  SacGuessResult,
  SacStats,
  SacPlayoutStartResult,
  SacPlayoutMoveResult,
} from '../../api/training';

export interface SacDrillProps {
  filterEco?: string;
  onBack?: () => void;
}

export default function SacDrill({ filterEco, onBack }: SacDrillProps = {}) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [positions, setPositions] = useState<SacPosition[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [currentResult, setCurrentResult] = useState<SacGuessResult | null>(null);
  const [score, setScore] = useState(0);
  const [acceptableCount, setAcceptableCount] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [stats, setStats] = useState<SacStats | null>(null);

  // Playout state vs LC0
  const [inPlayout, setInPlayout] = useState(false);
  const [playoutLoading, setPlayoutLoading] = useState(false);
  const [playoutError, setPlayoutError] = useState<string | null>(null);
  const [playoutState, setPlayoutState] = useState<SacPlayoutStartResult | SacPlayoutMoveResult | null>(null);
  const [playoutLine, setPlayoutLine] = useState<string[]>([]);
  const [playoutHistory, setPlayoutHistory] = useState<string[]>([]);
  const [playoutLastMoveResult, setPlayoutLastMoveResult] = useState<SacPlayoutMoveResult | null>(null);

  const exitPlayout = () => {
    setInPlayout(false);
    setPlayoutLoading(false);
    setPlayoutError(null);
    setPlayoutState(null);
    setPlayoutLine([]);
    setPlayoutHistory([]);
    setPlayoutLastMoveResult(null);
  };

  const loadSession = async () => {
    try {
      setLoading(true);
      setError(null);
      setCurrentResult(null);
      setCurrentIndex(0);
      setScore(0);
      setAcceptableCount(0);
      setIsFinished(false);
      exitPlayout();

      const [sessionPositions, statsData] = await Promise.all([
        startSacSession(10, filterEco).catch(() => []),
        getSacStats().catch(() => null),
      ]);

      setPositions(sessionPositions);
      setStats(statsData);
    } catch (err: any) {
      console.error('Failed to start sacrifice drill session:', err);
      setError(err.message || 'Failed to start session');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSession();
  }, []);

  const handleGuess = async (uci: string) => {
    if (currentResult || submitting || isFinished || positions.length === 0) return;

    setSubmitting(true);
    setError(null);

    const currentPos = positions[currentIndex];
    try {
      const result = await submitSacGuess(currentPos.id, uci);
      setCurrentResult(result);
      if (result.correct) {
        setScore((s) => s + 1);
      } else if (result.acceptable) {
        setAcceptableCount((a) => a + 1);
      }
    } catch (err: any) {
      console.error('Failed to submit sacrifice guess:', err);
      setError(err.message || 'Failed to submit guess');
    } finally {
      setSubmitting(false);
    }
  };

  const handleNext = async () => {
    setCurrentResult(null);
    exitPlayout();

    if (currentIndex + 1 < positions.length) {
      setCurrentIndex((prev) => prev + 1);
    } else {
      setIsFinished(true);
      const updatedStats = await getSacStats().catch(() => null);
      if (updatedStats) setStats(updatedStats);
    }
  };

  const handleStartPlayout = async () => {
    const currentPos = positions[currentIndex];
    if (!currentPos) return;

    setPlayoutLoading(true);
    setPlayoutError(null);

    try {
      const res = await startSacPlayout(currentPos.id);
      if (res.error === 'engine_unavailable') {
        setPlayoutError('Engine offline — play-out unavailable');
        setPlayoutLoading(false);
        return;
      }

      setPlayoutState(res);
      setPlayoutLine(res.line || []);
      setPlayoutHistory([]);
      setPlayoutLastMoveResult(null);
      setInPlayout(true);
    } catch (err: any) {
      console.error('Failed to start sacrifice playout:', err);
      setPlayoutError(err.message || 'Failed to start engine play-out');
    } finally {
      setPlayoutLoading(false);
    }
  };

  const handleAttackMove = async (uci: string) => {
    if (playoutLoading || !playoutState || playoutState.is_complete) return;

    const currentPos = positions[currentIndex];
    if (!currentPos) return;

    setPlayoutLoading(true);
    setPlayoutError(null);

    try {
      const res = await submitPlayoutMove(
        currentPos.id,
        playoutLine,
        uci,
        playoutHistory
      );

      if (res.error === 'engine_unavailable') {
        setPlayoutError('Engine offline — play-out unavailable');
        return;
      }

      const quality = res.quality || 'ok';
      const updatedHistory = [...playoutHistory, quality];
      setPlayoutHistory(updatedHistory);
      setPlayoutLine(res.line || [...playoutLine, uci]);
      setPlayoutState(res);
      setPlayoutLastMoveResult(res);
    } catch (err: any) {
      console.error('Failed to submit playout move:', err);
      setPlayoutError(err.message || 'Illegal or invalid move');
    } finally {
      setPlayoutLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="sac-drill-panel glass-panel">
        <p>Loading sacrifice drill session...</p>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="sac-drill-panel glass-panel">
        <h2 className="gradient-text">Sharp Positions & Tactical Landmines</h2>
        <p className="empty-state-msg">
          No eligible sharp positions found in profile. Run a diagnosis first to discover your landmines!
        </p>
        <button className="glass-btn primary" onClick={loadSession}>
          Try Again
        </button>
      </div>
    );
  }

  if (isFinished) {
    const sessionAccuracy = positions.length > 0 ? (score / positions.length) * 100 : 0;
    return (
      <div className="sac-drill-panel glass-panel" style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
        <h2 className="gradient-text">Session Complete!</h2>
        <div style={{ fontSize: '2.5rem', fontWeight: 'bold', margin: '20px 0', color: '#60a5fa' }}>
          {score} / {positions.length}
        </div>
        <p style={{ fontSize: '1.2rem', marginBottom: '10px' }}>
          Sacrifice Finding Accuracy: <strong>{sessionAccuracy.toFixed(1)}%</strong>
        </p>
        {acceptableCount > 0 && (
          <p style={{ fontSize: '0.95rem', color: '#f59e0b', marginBottom: '20px' }}>
            ⚡ Found <strong>{acceptableCount}</strong> sound alternative sharp moves!
          </p>
        )}

        {stats && (
          <div className="glass-panel" style={{ padding: '15px', marginBottom: '25px', textAlign: 'left' }}>
            <h3 style={{ marginTop: 0, fontSize: '1rem', color: '#60a5fa' }}>Lifetime Sacrifice Stats</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>Overall Accuracy</span>
                <div style={{ fontSize: '1.3rem', fontWeight: 600 }}>{(stats.accuracy * 100).toFixed(1)}%</div>
                <div style={{ fontSize: '0.75rem', opacity: 0.6 }}>({stats.correct} / {stats.total} guesses)</div>
              </div>
              <div>
                <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>Recent Accuracy (last 50)</span>
                <div style={{ fontSize: '1.3rem', fontWeight: 600, color: '#f59e0b' }}>
                  {(stats.recent_accuracy * 100).toFixed(1)}%
                </div>
                <div style={{ fontSize: '0.75rem', opacity: 0.6 }}>({stats.acceptable} sound alts)</div>
              </div>
            </div>
          </div>
        )}

        <button className="glass-btn primary" onClick={loadSession} style={{ padding: '10px 24px', fontSize: '1rem' }}>
          Start New Session
        </button>
      </div>
    );
  }

  const currentPos = positions[currentIndex];
  const sideToMove = currentPos.fen.split(' ')[1] === 'b' ? 'black' : 'white';

  // Render Playout Mode vs LC0
  if (inPlayout && playoutState) {
    const attackerColor = playoutState.attacker_is_white ? 'white' : 'black';
    const isComplete = playoutState.is_complete;
    const currentEval = playoutState.attacker_eval_cp ?? 0;
    const evalDisplay = `${currentEval >= 0 ? '+' : ''}${currentEval}cp`;

    return (
      <div className="sac-drill-panel glass-panel">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
          <div>
            <h2 className="gradient-text" style={{ margin: 0, fontSize: '1.4rem' }}>
              ⚔️ Sacrifice Playout vs LC0
            </h2>
            <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>
              Attacker: {attackerColor.toUpperCase()} • Position {currentIndex + 1} of {positions.length}
            </span>
          </div>
          <button className="glass-btn" onClick={exitPlayout} style={{ fontSize: '0.85rem', padding: '6px 12px' }}>
            Back to Sacrifices
          </button>
        </div>

        {playoutError && (
          <div style={{ color: '#ef4444', marginBottom: '10px', fontSize: '0.95rem' }}>
            {playoutError}
          </div>
        )}

        {/* Eval and Playout Feedback Header */}
        <div
          className="glass-panel"
          style={{
            padding: '12px 16px',
            marginBottom: '15px',
            backgroundColor: 'rgba(30, 41, 59, 0.7)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '10px',
          }}
        >
          <div>
            <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>Attacker Eval: </span>
            <strong style={{ fontSize: '1.1rem', color: currentEval >= 0 ? '#6ee7b7' : '#fca5a5' }}>
              {evalDisplay}
            </strong>
            <span style={{ fontSize: '0.8rem', opacity: 0.6, marginLeft: '6px' }}>
              ({currentEval >= 0 ? 'Attack working' : 'Defense holding'})
            </span>
          </div>

          {playoutLastMoveResult && playoutLastMoveResult.quality && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span
                style={{
                  padding: '4px 10px',
                  borderRadius: '12px',
                  fontSize: '0.85rem',
                  fontWeight: 600,
                  backgroundColor:
                    playoutLastMoveResult.quality === 'great'
                      ? 'rgba(16, 185, 129, 0.25)'
                      : playoutLastMoveResult.quality === 'ok'
                      ? 'rgba(245, 158, 11, 0.25)'
                      : 'rgba(239, 68, 68, 0.25)',
                  color:
                    playoutLastMoveResult.quality === 'great'
                      ? '#6ee7b7'
                      : playoutLastMoveResult.quality === 'ok'
                      ? '#fcd34d'
                      : '#fca5a5',
                  border: `1px solid ${
                    playoutLastMoveResult.quality === 'great'
                      ? '#10b981'
                      : playoutLastMoveResult.quality === 'ok'
                      ? '#f59e0b'
                      : '#ef4444'
                  }`,
                }}
              >
                {playoutLastMoveResult.quality === 'great' && '🟢 Great Move!'}
                {playoutLastMoveResult.quality === 'ok' && '🟡 OK Move'}
                {playoutLastMoveResult.quality === 'drift' && '🔴 Drift'}
              </span>

              {playoutLastMoveResult.quality !== 'great' && playoutLastMoveResult.lc0_best_attack && (
                <span style={{ fontSize: '0.85rem', color: '#cbd5e1' }}>
                  LC0 preferred {playoutLastMoveResult.lc0_best_attack.san}
                </span>
              )}
            </div>
          )}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}>
          <div style={{ width: '100%', maxWidth: '480px', aspectRatio: '1/1' }}>
            <TrainingBoard
              fen={playoutState.fen || currentPos.fen}
              orientation={attackerColor}
              interactive={Boolean(playoutState.user_to_move && !isComplete && !playoutLoading)}
              onMove={(uci) => handleAttackMove(uci)}
            />
          </div>

          {/* Playout Summary Verdict Card on completion */}
          {isComplete && playoutState.summary && (
            <div className="glass-panel" style={{ width: '100%', maxWidth: '520px', padding: '16px', textAlign: 'center' }}>
              <h3 className="gradient-text" style={{ marginTop: 0, fontSize: '1.3rem' }}>
                Playout Complete
              </h3>
              <div
                style={{
                  padding: '10px 14px',
                  borderRadius: '8px',
                  marginBottom: '15px',
                  fontWeight: 600,
                  fontSize: '1.05rem',
                  backgroundColor: 'rgba(96, 165, 250, 0.15)',
                  color: '#60a5fa',
                  border: '1px solid #3b82f6',
                }}
              >
                {playoutState.summary.verdict}
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginBottom: '15px', fontSize: '0.85rem' }}>
                <div style={{ background: 'rgba(255,255,255,0.05)', padding: '8px', borderRadius: '6px' }}>
                  <div>Moves</div>
                  <strong style={{ fontSize: '1.1rem' }}>{playoutState.summary.moves}</strong>
                </div>
                <div style={{ background: 'rgba(16,185,129,0.1)', padding: '8px', borderRadius: '6px', color: '#6ee7b7' }}>
                  <div>Great 🟢</div>
                  <strong style={{ fontSize: '1.1rem' }}>{playoutState.summary.great}</strong>
                </div>
                <div style={{ background: 'rgba(245,158,11,0.1)', padding: '8px', borderRadius: '6px', color: '#fcd34d' }}>
                  <div>OK 🟡</div>
                  <strong style={{ fontSize: '1.1rem' }}>{playoutState.summary.ok}</strong>
                </div>
                <div style={{ background: 'rgba(239,68,68,0.1)', padding: '8px', borderRadius: '6px', color: '#fca5a5' }}>
                  <div>Drift 🔴</div>
                  <strong style={{ fontSize: '1.1rem' }}>{playoutState.summary.drift}</strong>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '10px' }}>
                <button
                  className="glass-btn"
                  onClick={exitPlayout}
                  style={{ flex: 1, padding: '10px', fontSize: '0.95rem' }}
                >
                  Back to sacrifices
                </button>
                <button
                  className="glass-btn primary"
                  onClick={handleNext}
                  style={{ flex: 1, padding: '10px', fontSize: '0.95rem' }}
                >
                  {currentIndex + 1 < positions.length ? 'Next Position' : 'Finish Session'}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="sac-drill-panel glass-panel">
      {/* Session Progress Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <div>
          <h2 className="gradient-text" style={{ margin: 0, fontSize: '1.4rem' }}>
            {filterEco ? `⚔️ ${filterEco} Sharp Positions Training` : 'Sharp Positions & Tactical-Landmine Training'}
          </h2>
          <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>
            Position {currentIndex + 1} of {positions.length} • Found: {score}
          </span>
        </div>
        {onBack && (
          <button className="glass-btn" onClick={onBack} style={{ fontSize: '0.85rem', padding: '6px 12px' }}>
            ← Back to Sharp Openings
          </button>
        )}
      </div>

      {/* Prompt Banner */}
      <div
        className="glass-panel"
        style={{
          padding: '10px 16px',
          marginBottom: '15px',
          backgroundColor: 'rgba(96, 165, 250, 0.15)',
          borderLeft: '4px solid #60a5fa',
          fontWeight: 600,
          fontSize: '1.05rem',
        }}
      >
        💡 A sharp tactical continuation is available here — find it.
      </div>

      {error && <div style={{ color: '#ef4444', marginBottom: '10px' }}>{error}</div>}

      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '20px' }}>
        <div style={{ width: '100%', maxWidth: '480px', aspectRatio: '1/1' }}>
          <TrainingBoard
            fen={currentPos.fen}
            orientation={sideToMove}
            interactive={!currentResult && !submitting}
            onMove={(uci) => handleGuess(uci)}
          />
        </div>

        {/* Soundness Reveal Panel */}
        {currentResult && (
          <div className="glass-panel" style={{ width: '100%', maxWidth: '520px', padding: '16px' }}>
            {/* Verdict Banner */}
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                marginBottom: '15px',
                fontWeight: 600,
                backgroundColor: currentResult.correct
                  ? 'rgba(16, 185, 129, 0.2)'
                  : currentResult.acceptable
                  ? 'rgba(245, 158, 11, 0.2)'
                  : 'rgba(239, 68, 68, 0.2)',
                color: currentResult.correct
                  ? '#6ee7b7'
                  : currentResult.acceptable
                  ? '#fcd34d'
                  : '#fca5a5',
                border: `1px solid ${
                  currentResult.correct ? '#10b981' : currentResult.acceptable ? '#f59e0b' : '#ef4444'
                }`,
              }}
            >
              {currentResult.correct ? (
                <span>🎯 HIT! You found the sharp move! ({currentResult.sac_move.san})</span>
              ) : currentResult.acceptable ? (
                <span>⚡ SOUND ALTERNATIVE! A sharp try — LC0 preferred {currentResult.sac_move.san}.</span>
              ) : (
                <span>❌ MISS! You played it safe. The sharp move was {currentResult.sac_move.san}.</span>
              )}
            </div>

            {/* Soundness Framing Comparison */}
            <div
              style={{
                backgroundColor: 'rgba(255, 255, 255, 0.05)',
                padding: '12px 14px',
                borderRadius: '6px',
                fontSize: '0.92rem',
                lineHeight: '1.5',
                marginBottom: '15px',
                borderLeft: '3px solid #60a5fa',
              }}
            >
              You'd safely play <strong>{currentResult.safe_move.san}</strong> ({currentResult.safe_move.eval_cp}cp). The sac <strong>{currentResult.sac_move.san}</strong> ({currentResult.sac_move.eval_cp}cp) concedes only <strong>{currentResult.eval_loss_cp}cp</strong> of objective eval but goes into a far sharper position (complexity {currentResult.sac_move.complexity.toFixed(2)}) where the opponent is likely to go wrong.
            </div>

            {playoutError && (
              <div style={{ color: '#ef4444', marginBottom: '10px', fontSize: '0.9rem' }}>
                {playoutError}
              </div>
            )}

            <div style={{ display: 'flex', gap: '10px', width: '100%' }}>
              <button
                className="glass-btn secondary"
                onClick={handleStartPlayout}
                disabled={playoutLoading}
                style={{
                  flex: 1,
                  padding: '10px',
                  fontSize: '0.95rem',
                  backgroundColor: 'rgba(124, 58, 237, 0.25)',
                  border: '1px solid #8b5cf6',
                  color: '#c4b5fd',
                }}
              >
                {playoutLoading ? 'Starting LC0...' : '▶ Play it out vs LC0'}
              </button>
              <button
                className="glass-btn primary"
                onClick={handleNext}
                style={{ flex: 1, padding: '10px', fontSize: '0.95rem' }}
              >
                {currentIndex + 1 < positions.length ? 'Next Position' : 'Finish Session'}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
