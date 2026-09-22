import { useState, useEffect, useRef } from 'react';
import TrainingBoard from './TrainingBoard';
import {
  startIntuitionSession,
  submitIntuitionGuess,
  getIntuitionStats,
} from '../../api/training';
import type {
  IntuitionPosition,
  IntuitionGuessResult,
  IntuitionStats,
} from '../../api/training';

export const INTUITION_SECONDS = 10;

export default function IntuitionDrill() {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [positions, setPositions] = useState<IntuitionPosition[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [timeLeft, setTimeLeft] = useState(INTUITION_SECONDS);
  const [currentResult, setCurrentResult] = useState<IntuitionGuessResult | null>(null);
  const [score, setScore] = useState(0);
  const [isFinished, setIsFinished] = useState(false);
  const [stats, setStats] = useState<IntuitionStats | null>(null);

  const timerRef = useRef<NodeJS.Timeout | null>(null);

  const loadSession = async () => {
    try {
      setLoading(true);
      setError(null);
      setCurrentResult(null);
      setCurrentIndex(0);
      setScore(0);
      setIsFinished(false);
      setTimeLeft(INTUITION_SECONDS);

      const [sessionPositions, statsData] = await Promise.all([
        startIntuitionSession(12).catch(() => []),
        getIntuitionStats().catch(() => null),
      ]);

      setPositions(sessionPositions);
      setStats(statsData);
    } catch (err: any) {
      console.error('Failed to start intuition session:', err);
      setError(err.message || 'Failed to start session');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSession();
  }, []);

  // Timer countdown effect
  useEffect(() => {
    if (loading || isFinished || currentResult || submitting || positions.length === 0) {
      if (timerRef.current) clearInterval(timerRef.current);
      return;
    }

    timerRef.current = setInterval(() => {
      setTimeLeft((prev) => {
        if (prev <= 1) {
          if (timerRef.current) clearInterval(timerRef.current);
          handleTimeout();
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [currentIndex, currentResult, loading, isFinished, submitting, positions]);

  const handleGuess = async (uci: string) => {
    if (currentResult || submitting || isFinished || positions.length === 0) return;

    if (timerRef.current) clearInterval(timerRef.current);
    setSubmitting(true);
    setError(null);

    const currentPos = positions[currentIndex];
    try {
      const result = await submitIntuitionGuess(currentPos.epd, uci);
      setCurrentResult(result);
      if (result.correct) {
        setScore((s) => s + 1);
      }
    } catch (err: any) {
      console.error('Failed to submit guess:', err);
      setError(err.message || 'Failed to submit guess');
    } finally {
      setSubmitting(false);
    }
  };

  const handleTimeout = () => {
    handleGuess('');
  };

  const handleNext = async () => {
    setCurrentResult(null);
    if (currentIndex + 1 < positions.length) {
      setCurrentIndex((prev) => prev + 1);
      setTimeLeft(INTUITION_SECONDS);
    } else {
      setIsFinished(true);
      const updatedStats = await getIntuitionStats().catch(() => null);
      if (updatedStats) setStats(updatedStats);
    }
  };

  if (loading) {
    return (
      <div className="intuition-panel glass-panel">
        <p>Loading intuition session...</p>
      </div>
    );
  }

  if (positions.length === 0) {
    return (
      <div className="intuition-panel glass-panel">
        <h2 className="gradient-text">LC0 Intuition Speed-Drill</h2>
        <p className="empty-state-msg">No eligible positions found in cache. Run a diagnosis first to populate positions!</p>
        <button className="glass-btn primary" onClick={loadSession}>
          Try Again
        </button>
      </div>
    );
  }

  if (isFinished) {
    const sessionAccuracy = positions.length > 0 ? (score / positions.length) * 100 : 0;
    return (
      <div className="intuition-panel glass-panel" style={{ maxWidth: '600px', margin: '0 auto', textAlign: 'center' }}>
        <h2 className="gradient-text">Session Complete!</h2>
        <div style={{ fontSize: '2.5rem', fontWeight: 'bold', margin: '20px 0', color: '#60a5fa' }}>
          {score} / {positions.length}
        </div>
        <p style={{ fontSize: '1.2rem', marginBottom: '20px' }}>
          Session Top-1 Accuracy: <strong>{sessionAccuracy.toFixed(1)}%</strong>
        </p>

        {stats && (
          <div className="glass-panel" style={{ padding: '15px', marginBottom: '25px', textAlign: 'left' }}>
            <h3 style={{ marginTop: 0, fontSize: '1rem', color: '#60a5fa' }}>Lifetime Intuition Stats</h3>
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

  return (
    <div className="intuition-panel glass-panel">
      {/* Session Progress Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <div>
          <h2 className="gradient-text" style={{ margin: 0, fontSize: '1.4rem' }}>
            LC0 Intuition Speed-Drill
          </h2>
          <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>
            Position {currentIndex + 1} of {positions.length} • Score: {score}
          </span>
        </div>

        {/* 10s Timer Display */}
        <div
          style={{
            fontSize: '1.4rem',
            fontWeight: 'bold',
            padding: '6px 14px',
            borderRadius: '8px',
            backgroundColor: timeLeft <= 3 ? 'rgba(239, 68, 68, 0.3)' : 'rgba(255, 255, 255, 0.1)',
            color: timeLeft <= 3 ? '#ef4444' : '#60a5fa',
            border: `1px solid ${timeLeft <= 3 ? '#ef4444' : 'rgba(96, 165, 250, 0.3)'}`,
          }}
        >
          ⏱️ {timeLeft}s
        </div>
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

        {/* Reveal Panel */}
        {currentResult && (
          <div className="glass-panel" style={{ width: '100%', maxWidth: '520px', padding: '16px' }}>
            <div
              style={{
                padding: '10px 14px',
                borderRadius: '8px',
                marginBottom: '15px',
                fontWeight: 600,
                backgroundColor: currentResult.correct ? 'rgba(16, 185, 129, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                color: currentResult.correct ? '#6ee7b7' : '#fca5a5',
                border: `1px solid ${currentResult.correct ? '#10b981' : '#ef4444'}`,
              }}
            >
              {currentResult.correct ? (
                <span>🎯 HIT! You guessed LC0's #1 policy move! ({currentResult.top_move.san} - {(currentResult.top_move.p * 100).toFixed(1)}%)</span>
              ) : currentResult.rank !== null ? (
                <span>
                  ❌ MISS! Your move ({currentResult.your_move?.san}) was LC0's #{currentResult.rank} choice (
                  {((currentResult.your_move?.p || 0) * 100).toFixed(1)}%). Top move: {currentResult.top_move.san} (
                  {(currentResult.top_move.p * 100).toFixed(1)}%).
                </span>
              ) : (
                <span>
                  ❌ MISS! Your move was not in LC0's top moves. Top move: {currentResult.top_move.san} (
                  {(currentResult.top_move.p * 100).toFixed(1)}%).
                </span>
              )}
            </div>

            {/* Top-5 Policy List */}
            <h4 style={{ margin: '0 0 10px 0', fontSize: '0.95rem', color: '#60a5fa' }}>LC0 Ranked Policy Top 5</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', marginBottom: '15px' }}>
              {currentResult.top_policy.map((m, idx) => {
                const isTop = idx === 0;
                const isYourMove = currentResult.your_move && currentResult.your_move.uci === m.uci;
                const pPct = (m.p * 100).toFixed(1);

                return (
                  <div
                    key={m.uci}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '10px',
                      fontSize: '0.9rem',
                      padding: '4px 8px',
                      borderRadius: '4px',
                      backgroundColor: isYourMove
                        ? 'rgba(245, 158, 11, 0.25)'
                        : isTop
                        ? 'rgba(16, 185, 129, 0.15)'
                        : 'rgba(255, 255, 255, 0.05)',
                    }}
                  >
                    <span style={{ width: '24px', opacity: 0.7 }}>#{idx + 1}</span>
                    <span style={{ width: '50px', fontWeight: 600 }}>{m.san}</span>
                    <div
                      style={{
                        flex: 1,
                        height: '14px',
                        backgroundColor: 'rgba(255, 255, 255, 0.1)',
                        borderRadius: '7px',
                        overflow: 'hidden',
                      }}
                    >
                      <div
                        style={{
                          width: `${Math.max(Number(pPct), 3)}%`,
                          height: '100%',
                          backgroundColor: isTop ? '#10b981' : isYourMove ? '#f59e0b' : '#60a5fa',
                          borderRadius: '7px',
                        }}
                      />
                    </div>
                    <span style={{ width: '55px', textAlign: 'right', fontWeight: 500 }}>{pPct}%</span>
                  </div>
                );
              })}
            </div>

            <button
              className="glass-btn primary"
              onClick={handleNext}
              style={{ width: '100%', padding: '10px', fontSize: '1rem' }}
            >
              {currentIndex + 1 < positions.length ? 'Next Position' : 'Finish Session'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
