import { useState, useEffect } from 'react';
import {
  getUsualSuspects,
  getApprovedSuspects,
  approveSuspects,
  buildSuspectsDeck,
  getDueDrills,
} from '../../api/training';
import type { UsualSuspectsResponse, UsualSuspect } from '../../api/training';

interface UsualSuspectsProps {
  onDeckBuilt: (setId: string) => void;
}

export default function UsualSuspects({ onDeckBuilt }: UsualSuspectsProps) {
  const [loading, setLoading] = useState(true);
  const [building, setBuilding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<UsualSuspectsResponse | null>(null);
  const [checkedThemes, setCheckedThemes] = useState<string[]>([]);
  const [dueCount, setDueCount] = useState<number>(0);

  useEffect(() => {
    async function loadData() {
      try {
        setLoading(true);
        setError(null);

        const [suspectsRes, approvedRes, dueRes] = await Promise.all([
          Promise.resolve(getUsualSuspects()).catch(() => null),
          Promise.resolve(getApprovedSuspects()).catch(() => ({ themes: [] })),
          Promise.resolve(getDueDrills()).catch(() => ({ count: 0 })),
        ]);

        setData(suspectsRes);
        setDueCount(dueRes ? dueRes.count : 0);

        if (suspectsRes && suspectsRes.suspects && suspectsRes.suspects.length > 0) {
          const storedApproved = approvedRes?.themes || [];
          if (storedApproved.length > 0) {
            setCheckedThemes(storedApproved);
          } else {
            // Default pre-check all suspects if none explicitly saved
            setCheckedThemes(suspectsRes.suspects.map((s: UsualSuspect) => s.theme));
          }
        }
      } catch (err: any) {
        console.error('Failed to load Usual Suspects data:', err);
        setError(err.message || 'Failed to load usual suspects');
      } finally {
        setLoading(false);
      }
    }

    loadData();
  }, []);

  const toggleTheme = (theme: string) => {
    setCheckedThemes((prev) =>
      prev.includes(theme) ? prev.filter((t) => t !== theme) : [...prev, theme]
    );
  };

  const handleBuildDeck = async () => {
    try {
      setBuilding(true);
      setError(null);

      // Approve checked themes
      await approveSuspects(checkedThemes);

      // Build blended deck
      const deck = await buildSuspectsDeck(20);

      if (deck && deck.id) {
        onDeckBuilt(deck.id);
      } else {
        throw new Error('No drill set ID returned from deck builder');
      }
    } catch (err: any) {
      console.error('Failed to build deck:', err);
      setError(err.message || 'Failed to build deck');
    } finally {
      setBuilding(false);
    }
  };

  if (loading) {
    return (
      <div className="usual-suspects-panel glass-panel">
        <p>Loading usual suspects...</p>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="usual-suspects-panel glass-panel">
        <h2 className="gradient-text">Usual Suspects</h2>
        <p className="empty-state-msg">Run a diagnosis first to discover your usual suspects.</p>
      </div>
    );
  }

  const { suspects } = data;

  if (!suspects || suspects.length === 0) {
    return (
      <div className="usual-suspects-panel glass-panel">
        <h2 className="gradient-text">Usual Suspects</h2>
        <p className="empty-state-msg">No recurring weaknesses detected yet (min 2 games floor).</p>
      </div>
    );
  }

  const topWeakness = suspects[0]?.theme || 'None';
  const themesAttention = suspects.slice(1, 4).map((s) => s.theme).join(', ') || 'None';

  return (
    <div className="usual-suspects-panel glass-panel">
      {/* Compact Dashboard Header */}
      <div className="suspects-dashboard-summary glass-panel" style={{ marginBottom: '20px', padding: '15px' }}>
        <h3 style={{ margin: '0 0 10px 0', fontSize: '1.1rem', color: 'var(--color-primary-light, #60a5fa)' }}>
          Weakness Summary Dashboard
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px' }}>
          <div>
            <span style={{ fontSize: '0.8rem', opacity: 0.7, display: 'block' }}>Top Weakness</span>
            <strong style={{ fontSize: '1rem', color: '#f87171' }}>{topWeakness}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', opacity: 0.7, display: 'block' }}>Needs Attention</span>
            <strong style={{ fontSize: '0.95rem' }}>{themesAttention}</strong>
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', opacity: 0.7, display: 'block' }}>Opening Focus</span>
            <span style={{ fontSize: '0.9rem', fontStyle: 'italic', opacity: 0.8 }}>Openings pending ECO fix</span>
          </div>
          <div>
            <span style={{ fontSize: '0.8rem', opacity: 0.7, display: 'block' }}>SRS Due Drills</span>
            <strong style={{ fontSize: '1rem', color: dueCount > 0 ? '#fbbf24' : 'inherit' }}>
              {dueCount} due
            </strong>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
        <h2 className="gradient-text" style={{ margin: 0 }}>Recurring Weaknesses ("Usual Suspects")</h2>
        <button
          className="glass-btn primary"
          onClick={handleBuildDeck}
          disabled={building || checkedThemes.length === 0}
        >
          {building ? 'Building Deck...' : 'Build my training deck'}
        </button>
      </div>

      {error && <div className="error-msg" style={{ marginBottom: '15px', color: 'var(--color-danger, #ef4444)' }}>{error}</div>}

      <div className="suspect-cards-list" style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {suspects.map((s: UsualSuspect) => {
          const isChecked = checkedThemes.includes(s.theme);
          return (
            <div
              key={s.theme}
              className="suspect-card glass-panel"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '12px 16px',
                borderLeft: `4px solid ${
                  s.severity_label === 'high'
                    ? '#ef4444'
                    : s.severity_label === 'medium'
                    ? '#f59e0b'
                    : '#10b981'
                }`,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <input
                  type="checkbox"
                  id={`suspect-${s.theme}`}
                  checked={isChecked}
                  onChange={() => toggleTheme(s.theme)}
                  style={{ width: '18px', height: '18px', cursor: 'pointer' }}
                />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <label
                      htmlFor={`suspect-${s.theme}`}
                      style={{ fontWeight: 600, fontSize: '1.05rem', cursor: 'pointer' }}
                    >
                      {s.theme}
                    </label>
                    <span
                      className={`severity-badge ${s.severity_label}`}
                      style={{
                        fontSize: '0.75rem',
                        padding: '2px 8px',
                        borderRadius: '12px',
                        textTransform: 'uppercase',
                        fontWeight: 600,
                        backgroundColor:
                          s.severity_label === 'high'
                            ? 'rgba(239, 68, 68, 0.2)'
                            : s.severity_label === 'medium'
                            ? 'rgba(245, 158, 11, 0.2)'
                            : 'rgba(16, 185, 129, 0.2)',
                        color:
                          s.severity_label === 'high'
                            ? '#fca5a5'
                            : s.severity_label === 'medium'
                            ? '#fcd34d'
                            : '#6ee7b7',
                      }}
                    >
                      {s.severity_label}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.85rem', opacity: 0.8, marginTop: '4px' }}>
                    {s.games} games • {s.occurrences} occurrences
                  </div>
                </div>
              </div>

              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>Score: {s.rank_score}</div>
                <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>Mean Sev: {s.mean_severity}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
