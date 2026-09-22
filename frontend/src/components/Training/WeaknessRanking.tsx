import { useEffect, useState } from 'react';
import { getWeaknessRanking } from '../../api/training';

export interface RankingItem {
  dim: string;
  value: number;
  count: number;
  ref_value: number;
  grade: number;
  importance: number;
  kind: 'weakness' | 'strength';
}

export interface WeaknessRankingData {
  ranking: RankingItem[];
  phase: RankingItem[];
  clock: RankingItem[];
}

function formatDimLabel(section: 'openings' | 'phase' | 'clock', dim: string): string {
  if (section === 'phase') {
    const lower = dim.toLowerCase();
    if (lower === 'opening') return 'Opening';
    if (lower === 'middlegame') return 'Middlegame';
    if (lower === 'endgame') return 'Endgame';
    return dim.charAt(0).toUpperCase() + dim.slice(1);
  }
  if (section === 'clock') {
    const lower = dim.toLowerCase();
    if (lower === 'fast') return 'Under time pressure (<1 min)';
    if (lower === 'normal') return 'Normal (1–3 min)';
    if (lower === 'slow') return 'Plenty of time (>3 min)';
    return dim;
  }
  return dim;
}

export default function WeaknessRanking() {
  const [data, setData] = useState<WeaknessRankingData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    getWeaknessRanking(6)
      .then((res) => {
        if (isMounted) {
          setData({
            ranking: res.ranking || [],
            phase: res.phase || [],
            clock: res.clock || [],
          });
          setLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          setError(err?.message || 'Failed to load weakness ranking.');
          setLoading(false);
        }
      });
    return () => {
      isMounted = false;
    };
  }, []);

  const ranking = data?.ranking || [];
  const phase = data?.phase || [];
  const clock = data?.clock || [];

  const allEmpty = data !== null && ranking.length === 0 && phase.length === 0 && clock.length === 0;

  const sections: {
    key: 'openings' | 'phase' | 'clock';
    title: string;
    items: RankingItem[];
    emptyNote: string;
  }[] = [
    {
      key: 'openings',
      title: 'Openings',
      items: ranking,
      emptyNote: 'Not enough games analyzed yet to rank your openings',
    },
    {
      key: 'phase',
      title: 'Game Phase',
      items: phase,
      emptyNote: 'Run a fresh diagnosis to rank by game phase',
    },
    {
      key: 'clock',
      title: 'Time Pressure',
      items: clock,
      emptyNote: 'Run a fresh diagnosis to rank by time pressure',
    },
  ];

  return (
    <div className="glass-panel weakness-ranking-panel" data-testid="weakness-ranking-panel">
      <h3>What to Work On</h3>
      <p className="ranking-subtext">Openings ranked by self-relative blindness versus your baseline</p>

      {loading && (
        <div className="ranking-loading" data-testid="ranking-loading">
          <div className="spinner" />
          <span>Analyzing opening performance...</span>
        </div>
      )}

      {error && !loading && (
        <div className="ranking-error error-msg" data-testid="ranking-error">
          {error}
        </div>
      )}

      {!loading && !error && allEmpty && (
        <div className="ranking-empty" data-testid="ranking-empty">
          Not enough games analyzed yet to rank your openings
        </div>
      )}

      {!loading && !error && !allEmpty && (
        <div className="ranking-sections" style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem', marginTop: '1rem' }}>
          {sections.map((sec) => (
            <div key={sec.key} className="ranking-section" data-testid={`ranking-section-${sec.key}`}>
              <h4 style={{ margin: '0 0 0.5rem 0', color: '#94a3b8', fontSize: '0.95rem', fontWeight: 600 }}>
                {sec.title}
              </h4>

              {sec.items.length > 0 ? (
                <div
                  className="ranking-list"
                  data-testid={sec.key === 'openings' ? 'ranking-list' : `ranking-list-${sec.key}`}
                  style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}
                >
                  {sec.items.map((item) => (
                    <div
                      key={`${sec.key}-${item.dim}`}
                      className={`ranking-item ${item.kind}`}
                      data-testid={`ranking-item-${item.dim}`}
                    >
                      <div className="ranking-item-main">
                        <span className="ranking-eco">{formatDimLabel(sec.key, item.dim)}</span>
                        <span className={`ranking-badge ${item.kind}`}>
                          {item.kind === 'weakness' ? 'Weakness' : 'Strength'}
                        </span>
                      </div>
                      <div className="ranking-item-stats">
                        <span className="stat-pill">
                          <strong>{(item.value * 100).toFixed(1)}%</strong> blind
                        </span>
                        <span className="stat-pill">
                          <strong>{item.count}</strong> {item.count === 1 ? 'game' : 'games'}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div
                  className="ranking-empty ranking-section-empty"
                  data-testid={sec.key === 'openings' ? 'ranking-empty' : `${sec.key}-empty`}
                  style={{ fontSize: '0.85rem', color: '#64748b', fontStyle: 'italic', padding: '0.4rem 0' }}
                >
                  {sec.emptyNote}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

