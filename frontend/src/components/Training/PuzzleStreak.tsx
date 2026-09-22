import { useState, useEffect } from 'react';
import {
  listPuzzleSets,
  createPuzzleSet,
  deletePuzzleSet,
  startPuzzleSession,
  submitPuzzleMove,
  nextPuzzle,
  type PuzzlePayload,
  type PuzzleSetMetadata,
} from '../../api/training';
import TrainingBoard from './TrainingBoard';
import { Chess } from 'chessops/chess';
import { parseFen, makeFen } from 'chessops/fen';
import { parseUci } from 'chessops/util';
import type { Key } from 'chessground/types';
import './Training.css';

interface PuzzleStreakProps {
  onExit?: () => void;
}

function applyUci(fen: string, uci: string): string {
  try {
    const pos = Chess.fromSetup(parseFen(fen).unwrap()).unwrap();
    const move = parseUci(uci);
    if (move) pos.play(move);
    return makeFen(pos.toSetup());
  } catch {
    return fen;
  }
}

export default function PuzzleStreak({ onExit }: PuzzleStreakProps) {
  const [sets, setSets] = useState<PuzzleSetMetadata[]>([]);
  const [selectedSetId, setSelectedSetId] = useState<string | null>(null);
  const [activeSession, setActiveSession] = useState<PuzzlePayload | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Set creation form state
  const [setName, setSetName] = useState('');
  const [minRating, setMinRating] = useState(1500);
  const [maxRating, setMaxRating] = useState(2000);
  const [setSize, setSetSize] = useState(100);
  const [isCreating, setIsCreating] = useState(false);

  // Board state
  const [activeFen, setActiveFen] = useState<string>('');
  const [activeLastMove, setActiveLastMove] = useState<[Key, Key] | undefined>();
  const [isAnimating, setIsAnimating] = useState(false);
  const [attemptResult, setAttemptResult] = useState<PuzzlePayload | null>(null);

  const fetchSets = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listPuzzleSets();
      setSets(data);
      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to load puzzle sets');
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSets();
  }, []);

  const handleCreateSet = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!setName.trim()) return;
    try {
      setIsCreating(true);
      setError(null);
      await createPuzzleSet({
        name: setName.trim(),
        min_rating: Number(minRating),
        max_rating: Number(maxRating),
        size: Number(setSize),
      });
      setSetName('');
      await fetchSets();
      setIsCreating(false);
    } catch (err: any) {
      setError(err.message || 'Failed to create puzzle set');
      setIsCreating(false);
    }
  };

  const handleDeleteSet = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await deletePuzzleSet(id);
      await fetchSets();
    } catch (err: any) {
      setError(err.message || 'Failed to delete set');
    }
  };

  const handleStartSession = async (setId: string) => {
    try {
      setLoading(true);
      setError(null);
      setAttemptResult(null);
      const session = await startPuzzleSession(setId);
      setSelectedSetId(setId);
      setActiveSession(session);
      setActiveFen(session.fen);
      setActiveLastMove(undefined);
      setLoading(false);
    } catch (err: any) {
      setError(err.message || 'Failed to start streak session');
      setLoading(false);
    }
  };

  const handleMove = async (uci: string) => {
    if (!activeSession || !activeSession.alive || isAnimating || attemptResult?.solved) return;
    try {
      const sessionId = activeSession.id || activeSession.session_id;
      const res = await submitPuzzleMove(sessionId, uci);

      if (res.correct && !res.solved) {
        // Correct step mid-line: play solver move then auto-play opponent reply
        const fenAfterUser = applyUci(activeFen, uci);
        setActiveFen(fenAfterUser);
        setActiveLastMove([uci.slice(0, 2) as Key, uci.slice(2, 4) as Key]);
        setActiveSession(res);

        if (res.opponent_uci) {
          setIsAnimating(true);
          setTimeout(() => {
            setActiveFen(applyUci(fenAfterUser, res.opponent_uci!));
            setActiveLastMove([
              res.opponent_uci!.slice(0, 2) as Key,
              res.opponent_uci!.slice(2, 4) as Key,
            ]);
            setIsAnimating(false);
          }, 450);
        }
        return;
      }

      if (res.correct && res.solved) {
        // Puzzle solved
        const fenAfterUser = applyUci(activeFen, uci);
        setActiveFen(fenAfterUser);
        setActiveLastMove([uci.slice(0, 2) as Key, uci.slice(2, 4) as Key]);
        setAttemptResult(res);
        setActiveSession(res);

        // Auto-advance to next puzzle
        setTimeout(async () => {
          try {
            const next = await nextPuzzle(sessionId);
            setActiveSession(next);
            setAttemptResult(null);
            setActiveFen(next.fen);
            setActiveLastMove(undefined);
          } catch (err: any) {
            console.error('Failed to load next puzzle', err);
          }
        }, 1000);
        return;
      }

      // Wrong move -> streak ends
      setAttemptResult(res);
      setActiveSession(res);
    } catch (err: any) {
      console.error('Move submission failed', err);
    }
  };

  const handleResetSession = () => {
    setActiveSession(null);
    setAttemptResult(null);
    setSelectedSetId(null);
    fetchSets();
  };

  // ------------------------------------------------------------------
  // View 1: Set Picker & Creator
  // ------------------------------------------------------------------
  if (!activeSession) {
    return (
      <div className="puzzle-streak-picker glass-panel" style={{ maxWidth: '900px', margin: '0 auto' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
          <div>
            <h2 className="gradient-text" style={{ margin: 0 }}>🔥 Puzzle Streak</h2>
            <p style={{ margin: '0.25rem 0 0', color: 'rgba(255,255,255,0.7)', fontSize: '0.95rem' }}>
              Climb in difficulty across 50-point rating bands. One mistake ends the run.
            </p>
          </div>
          {onExit && (
            <button className="glass-btn" onClick={onExit}>
              Back
            </button>
          )}
        </div>

        {error && <div className="error-msg" style={{ color: 'var(--color-danger)', marginBottom: '1rem' }}>{error}</div>}

        {/* Set Creation Form */}
        <form
          onSubmit={handleCreateSet}
          className="glass-card"
          style={{ marginBottom: '2rem', display: 'flex', flexWrap: 'wrap', gap: '1rem', alignItems: 'flex-end' }}
        >
          <div style={{ flex: '1 1 200px' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem', color: 'rgba(255,255,255,0.8)' }}>
              Set Name
            </label>
            <input
              type="text"
              className="glass-input"
              placeholder="e.g. Band 1500-2000"
              value={setName}
              onChange={(e) => setSetName(e.target.value)}
              required
            />
          </div>
          <div style={{ width: '110px' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem', color: 'rgba(255,255,255,0.8)' }}>
              Min Rating
            </label>
            <input
              type="number"
              className="glass-input"
              value={minRating}
              onChange={(e) => setMinRating(Number(e.target.value))}
              min={500}
              max={3500}
              required
            />
          </div>
          <div style={{ width: '110px' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem', color: 'rgba(255,255,255,0.8)' }}>
              Max Rating
            </label>
            <input
              type="number"
              className="glass-input"
              value={maxRating}
              onChange={(e) => setMaxRating(Number(e.target.value))}
              min={500}
              max={3500}
              required
            />
          </div>
          <div style={{ width: '90px' }}>
            <label style={{ display: 'block', fontSize: '0.85rem', marginBottom: '0.25rem', color: 'rgba(255,255,255,0.8)' }}>
              Size
            </label>
            <input
              type="number"
              className="glass-input"
              value={setSize}
              onChange={(e) => setSetSize(Number(e.target.value))}
              min={10}
              max={1000}
              required
            />
          </div>
          <button type="submit" className="glass-btn primary" disabled={isCreating || !setName.trim()}>
            {isCreating ? 'Creating...' : '+ Create Set'}
          </button>
        </form>

        {/* Existing Sets List */}
        <h3 style={{ marginBottom: '1rem', color: 'rgba(255,255,255,0.9)' }}>Available Puzzle Sets</h3>
        {loading ? (
          <div>Loading sets...</div>
        ) : sets.length === 0 ? (
          <div style={{ padding: '2rem', textAlign: 'center', color: 'rgba(255,255,255,0.6)' }}>
            No puzzle sets created yet. Create a set above to start drilling!
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
            {sets.map((s) => (
              <div
                key={s.id}
                className="glass-card"
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  padding: '1rem 1.25rem',
                }}
              >
                <div>
                  <h4 style={{ margin: 0, fontSize: '1.1rem', color: '#38bdf8' }}>{s.name}</h4>
                  <div style={{ fontSize: '0.85rem', color: 'rgba(255,255,255,0.6)', marginTop: '0.25rem' }}>
                    Rating Band: {s.min_rating} – {s.max_rating} | Size: {s.size} puzzles
                    {s.created && ` | Created: ${new Date(s.created).toLocaleDateString()}`}
                  </div>
                </div>
                <div style={{ display: 'flex', gap: '0.5rem' }}>
                  <button
                    className="glass-btn primary"
                    onClick={() => handleStartSession(s.id)}
                    aria-label={`Start streak ${s.name}`}
                  >
                    Start Streak
                  </button>
                  <button
                    className="glass-btn"
                    style={{ color: 'rgba(255,100,100,0.8)' }}
                    onClick={(e) => handleDeleteSet(s.id, e)}
                    aria-label={`Delete set ${s.name}`}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  // ------------------------------------------------------------------
  // View 2: Active Streak Session
  // ------------------------------------------------------------------
  const currentSet = sets.find((s) => s.id === selectedSetId);
  const bandMin = currentSet?.min_rating || 1500;
  const bandMax = currentSet?.max_rating || 2000;
  const ratingProgress = Math.min(
    100,
    Math.max(0, Math.round(((activeSession.rating - bandMin) / (bandMax - bandMin)) * 100))
  );

  const isComplete = activeSession.completed || activeSession.index >= activeSession.total;
  const isFailed = !activeSession.alive;
  const isSolved = attemptResult?.solved;

  return (
    <div className="drill-mode">
      {/* Header Strip */}
      <div className="drill-header glass-panel" style={{ width: '100%' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1.5rem' }}>
            <div style={{ fontSize: '1.25rem', fontWeight: 'bold', color: '#f59e0b' }}>
              🔥 Streak: {activeSession.streak}
            </div>
            <div style={{ fontSize: '1rem', color: 'rgba(255,255,255,0.8)' }}>
              🏆 Best: {activeSession.best_streak}
            </div>
            <div style={{ fontSize: '1rem', color: '#38bdf8' }}>
              Rating: <strong>{activeSession.rating}</strong>
            </div>
            <div style={{ fontSize: '0.9rem', color: 'rgba(255,255,255,0.6)' }}>
              Puzzle {activeSession.index + 1} / {activeSession.total}
            </div>
          </div>

          <button className="glass-btn" onClick={handleResetSession}>
            End Streak & Exit
          </button>
        </div>

        {/* Rating Progress Climb Bar */}
        <div style={{ marginTop: '0.75rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: 'rgba(255,255,255,0.5)', marginBottom: '0.2rem' }}>
            <span>Climb: {bandMin}</span>
            <span>{activeSession.rating}</span>
            <span>{bandMax}</span>
          </div>
          <div
            style={{
              width: '100%',
              height: '6px',
              background: 'rgba(255,255,255,0.1)',
              borderRadius: '3px',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${ratingProgress}%`,
                height: '100%',
                background: 'linear-gradient(90deg, #38bdf8, #f59e0b)',
                transition: 'width 0.4s ease',
              }}
            />
          </div>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="drill-content">
        <div className="board-container">
          <TrainingBoard
            fen={activeFen}
            orientation={activeSession.orientation}
            interactive={activeSession.alive && !isSolved && !isAnimating && !isComplete}
            onMove={handleMove}
            lastMove={activeLastMove}
            blunderFlash={Boolean(attemptResult && !attemptResult.correct)}
          />
        </div>

        <div className="drill-sidebar glass-panel">
          {isComplete ? (
            <div className="result-card correct">
              <h2 className="gradient-text">Set Completed!</h2>
              <p>You solved all {activeSession.total} puzzles in this set!</p>
              <div style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: '1rem 0', color: '#f59e0b' }}>
                🔥 Final Streak: {activeSession.streak}
              </div>
              <button className="glass-btn primary" onClick={handleResetSession}>
                New Streak
              </button>
            </div>
          ) : isFailed ? (
            <div className="result-card incorrect" data-testid="streak-failed-card">
              <h3 style={{ color: 'var(--color-danger, #ef4444)' }}>
                Streak over — {attemptResult?.streak_ended_at ?? activeSession.streak} solved
              </h3>

              {attemptResult?.solution_san && (
                <div style={{ margin: '1rem 0', background: 'rgba(0,0,0,0.3)', padding: '0.75rem', borderRadius: '8px' }}>
                  <p style={{ margin: 0, fontSize: '0.9rem', color: 'rgba(255,255,255,0.8)' }}>
                    <strong>Solution:</strong> {attemptResult.solution_san}
                  </p>
                </div>
              )}

              {/* Themes revealed after failure */}
              {activeSession.themes && activeSession.themes.length > 0 && (
                <div className="tags" style={{ margin: '0.75rem 0' }} data-testid="puzzle-themes">
                  {activeSession.themes.map((t) => (
                    <span key={t} className="tag">
                      {t}
                    </span>
                  ))}
                </div>
              )}

              {activeSession.puzzle_url && (
                <p style={{ fontSize: '0.85rem', margin: '0.75rem 0' }}>
                  <a
                    href={activeSession.puzzle_url}
                    target="_blank"
                    rel="noreferrer"
                    style={{ color: '#38bdf8', textDecoration: 'underline' }}
                  >
                    View on Lichess ↗
                  </a>
                </p>
              )}

              <button className="glass-btn primary" style={{ marginTop: '1rem' }} onClick={handleResetSession}>
                New Streak
              </button>
            </div>
          ) : isSolved ? (
            <div className="result-card correct">
              <h3 style={{ color: '#22c55e' }}>Correct! 🔥 Streak: {activeSession.streak}</h3>
              <p style={{ color: 'rgba(255,255,255,0.7)', fontSize: '0.9rem' }}>Advancing to next puzzle...</p>

              {/* Themes revealed after solve */}
              {activeSession.themes && activeSession.themes.length > 0 && (
                <div className="tags" style={{ margin: '0.75rem 0' }} data-testid="puzzle-themes">
                  {activeSession.themes.map((t) => (
                    <span key={t} className="tag">
                      {t}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ) : (
            <div className="instruction">
              <h3>Your Turn</h3>
              <p style={{ color: 'rgba(255,255,255,0.85)', lineHeight: 1.5 }}>
                Find the best move ({activeSession.orientation === 'white' ? 'White' : 'Black'} to move).
              </p>
              {/* Note: Themes are kept hidden until solved or failed to avoid spoilers */}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
