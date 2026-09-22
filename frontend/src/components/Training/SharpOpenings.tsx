import { useState, useEffect } from 'react';
import {
  getOpeningSharpness,
  getOpeningRecommendations,
} from '../../api/training';
import type {
  OpeningSharpnessItem,
  OpeningRecommendationItem,
} from '../../api/training';
import SacDrill from './SacDrill';

export default function SharpOpenings() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [openings, setOpenings] = useState<OpeningSharpnessItem[]>([]);
  const [recommendations, setRecommendations] = useState<OpeningRecommendationItem[]>([]);
  const [selectedColor, setSelectedColor] = useState<'all' | 'white' | 'black'>('all');
  const [drillEco, setDrillEco] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [sharpRes, recRes] = await Promise.all([
        getOpeningSharpness().catch(() => ({ openings: [] })),
        getOpeningRecommendations(selectedColor === 'all' ? undefined : selectedColor).catch(() => ({ recommendations: [] })),
      ]);
      setOpenings(sharpRes.openings || []);
      setRecommendations(recRes.recommendations || []);
    } catch (err: any) {
      console.error('Failed to load sharp openings data:', err);
      setError(err.message || 'Failed to load sharp openings data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [selectedColor]);

  // If user clicked "Drill this opening", render SacDrill filtered to drillEco
  if (drillEco) {
    return (
      <SacDrill
        filterEco={drillEco}
        onBack={() => setDrillEco(null)}
      />
    );
  }

  const topOpening = openings.length > 0 ? openings[0] : null;

  return (
    <div className="sharp-openings-panel glass-panel" style={{ padding: '20px' }}>
      {/* Top Headline Banner */}
      <div className="glass-panel" style={{ padding: '16px 20px', marginBottom: '25px', backgroundColor: 'rgba(30, 41, 59, 0.7)' }}>
        <h2 className="gradient-text" style={{ margin: '0 0 6px 0', fontSize: '1.5rem' }}>
          ⚔️ Sharp Openings & Tactical Opportunities
        </h2>
        {topOpening && topOpening.sacs > 0 ? (
          <p style={{ margin: 0, fontSize: '1.1rem', color: '#f59e0b', fontWeight: 600 }}>
            🔥 Your {topOpening.name} ({topOpening.eco}) hides {topOpening.sacs} sharp positions you're not taking.
          </p>
        ) : (
          <p style={{ margin: 0, fontSize: '1rem', opacity: 0.85 }}>
            Discover where your repertoire can go sharp and explore high-energy 1.e4 gambits.
          </p>
        )}
      </div>

      {loading && (
        <div style={{ textAlign: 'center', padding: '40px 0', color: '#94a3b8' }}>
          Loading sharp openings profile...
        </div>
      )}

      {error && (
        <div style={{ color: '#ef4444', marginBottom: '20px' }}>
          {error}
        </div>
      )}

      {!loading && !error && (
        <>
          {/* Section 1: Your Repertoire Sharpness */}
          <div style={{ marginBottom: '35px' }}>
            <h3 style={{ fontSize: '1.2rem', color: '#60a5fa', marginBottom: '15px' }}>
              Your Openings Ranked by Tactical Sharpness
            </h3>

            {openings.length === 0 ? (
              <div className="glass-panel" style={{ padding: '20px', textAlign: 'center', color: '#94a3b8' }}>
                No analyzed sharp positions found yet. Diagnose more games to reveal your opening tactical profile!
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {openings.map((op) => (
                  <div
                    key={op.eco}
                    className="glass-panel"
                    style={{
                      padding: '14px 18px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      flexWrap: 'wrap',
                      gap: '12px',
                    }}
                  >
                    <div style={{ flex: '1 1 250px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '4px' }}>
                        <span
                          style={{
                            backgroundColor: 'rgba(96, 165, 250, 0.2)',
                            color: '#60a5fa',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontWeight: 'bold',
                            fontSize: '0.85rem',
                          }}
                        >
                          {op.eco}
                        </span>
                        <strong style={{ fontSize: '1.05rem' }}>{op.name}</strong>
                      </div>
                      <div style={{ fontSize: '0.85rem', color: '#94a3b8', display: 'flex', gap: '15px' }}>
                        <span>Mean Complexity: <strong style={{ color: '#e2e8f0' }}>{op.mean_complexity.toFixed(3)}</strong></span>
                        <span>Total Positions: <strong style={{ color: '#e2e8f0' }}>{op.n_positions}</strong></span>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '1.2rem', fontWeight: 'bold', color: op.sacs > 0 ? '#f59e0b' : '#94a3b8' }}>
                          {op.sacs} ⚔️
                        </div>
                        <div style={{ fontSize: '0.75rem', color: '#94a3b8' }}>sharp candidates</div>
                      </div>

                      <button
                        className="glass-btn"
                        onClick={() => setDrillEco(op.eco)}
                        disabled={op.sacs === 0}
                        style={{
                          padding: '8px 14px',
                          fontSize: '0.85rem',
                          fontWeight: 600,
                          backgroundColor: op.sacs > 0 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(255, 255, 255, 0.05)',
                          color: op.sacs > 0 ? '#fcd34d' : '#94a3b8',
                          borderColor: op.sacs > 0 ? '#f59e0b' : 'transparent',
                        }}
                      >
                        ⚔ Drill this opening's sharp positions
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Section 2: Dynamic Openings Recommendations */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px', flexWrap: 'wrap', gap: '10px' }}>
              <h3 style={{ fontSize: '1.2rem', color: '#60a5fa', margin: 0 }}>
                Dynamic Openings to Explore
              </h3>

              {/* Color filter toggle */}
              <div style={{ display: 'flex', gap: '6px' }}>
                {(['all', 'white', 'black'] as const).map((col) => (
                  <button
                    key={col}
                    className={`glass-btn ${selectedColor === col ? 'active' : ''}`}
                    onClick={() => setSelectedColor(col)}
                    style={{ padding: '4px 10px', fontSize: '0.8rem', textTransform: 'capitalize' }}
                  >
                    {col}
                  </button>
                ))}
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '16px' }}>
              {recommendations.map((rec) => (
                <div
                  key={rec.eco + rec.name}
                  className="glass-panel"
                  style={{
                    padding: '16px',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                      <span
                        style={{
                          backgroundColor: rec.color === 'white' ? 'rgba(255, 255, 255, 0.15)' : 'rgba(147, 51, 234, 0.2)',
                          color: rec.color === 'white' ? '#f8fafc' : '#c084fc',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontWeight: 'bold',
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                        }}
                      >
                        {rec.eco} • {rec.color}
                      </span>
                    </div>

                    <h4 style={{ margin: '0 0 8px 0', fontSize: '1.1rem', color: '#f8fafc' }}>
                      {rec.name}
                    </h4>

                    <p style={{ fontSize: '0.85rem', color: '#cbd5e1', marginBottom: '12px', lineHeight: 1.4 }}>
                      {rec.sac_idea}
                    </p>

                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '12px' }}>
                      {rec.themes.map((t) => (
                        <span
                          key={t}
                          style={{
                            fontSize: '0.7rem',
                            backgroundColor: 'rgba(96, 165, 250, 0.15)',
                            color: '#93c5fd',
                            padding: '2px 6px',
                            borderRadius: '4px',
                          }}
                        >
                          #{t}
                        </span>
                      ))}
                    </div>
                  </div>

                  <div
                    style={{
                      fontSize: '0.8rem',
                      color: '#94a3b8',
                      backgroundColor: 'rgba(0, 0, 0, 0.2)',
                      padding: '8px 10px',
                      borderRadius: '6px',
                      fontStyle: 'italic',
                    }}
                  >
                    💡 {rec.why}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
