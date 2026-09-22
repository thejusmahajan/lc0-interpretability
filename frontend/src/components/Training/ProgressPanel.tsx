

interface ProgressPanelProps {
  trends: any;
}

export default function ProgressPanel({ trends }: ProgressPanelProps) {
  if (!trends) return <div className="glass-panel">Loading trends...</div>;

  const { profiles, motif_blind_series, training, latest_regressions, srs_stats, sac_stats, intuition_stats } = trends;

  // Simple Blunder Rate (confirmed_per_100) trend over profiles
  const blunderRates = profiles?.map((p: any) => p.aggregates?.confirmed_per_100 || 0) || [];
  const maxRate = Math.max(...blunderRates, 1); // Avoid div by 0

  return (
    <div className="progress-panel">
      {/* Live Training Session Stats */}
      <div className="glass-panel" style={{ marginBottom: '20px' }}>
        <h3 className="gradient-text" style={{ marginTop: 0 }}>Active Training Performance</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '15px', marginTop: '12px' }}>
          <div className="glass-card" style={{ padding: '12px' }}>
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>SRS Drill Accuracy</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 600, color: '#38bdf8', marginTop: '4px' }}>
              {srs_stats?.accuracy != null ? `${(srs_stats.accuracy * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
              {srs_stats?.total || 0} total attempts
            </div>
          </div>
          <div className="glass-card" style={{ padding: '12px' }}>
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Sharp Drills Accuracy</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 600, color: '#f59e0b', marginTop: '4px' }}>
              {sac_stats?.accuracy != null ? `${(sac_stats.accuracy * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
              {sac_stats?.total || 0} solved / {sac_stats?.acceptable || 0} sound
            </div>
          </div>
          <div className="glass-card" style={{ padding: '12px' }}>
            <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Intuition Top-1 Hit Rate</span>
            <div style={{ fontSize: '1.4rem', fontWeight: 600, color: '#34d399', marginTop: '4px' }}>
              {intuition_stats?.accuracy != null ? `${(intuition_stats.accuracy * 100).toFixed(1)}%` : 'N/A'}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#64748b', marginTop: '2px' }}>
              {intuition_stats?.correct || 0} / {intuition_stats?.total || 0} position guesses
            </div>
          </div>
        </div>
      </div>

      {latest_regressions && latest_regressions.length > 0 && (
        <div className="regression-banner glass-panel" style={{ borderColor: 'var(--color-danger)', marginBottom: '20px' }}>
          <h3 style={{ color: 'var(--color-danger)', marginTop: 0 }}>⚠️ Attention Required</h3>
          <p>You've regressed on:</p>
          <div className="tags">
            {latest_regressions.map((r: string) => (
              <span key={r} className="tag" style={{ backgroundColor: 'var(--color-danger)' }}>{r}</span>
            ))}
          </div>
        </div>
      )}

      <div className="glass-panel">
        <h3 className="gradient-text">Blunder Rate Trend</h3>
        <div className="chart-container" style={{ display: 'flex', alignItems: 'flex-end', height: '100px', gap: '8px', padding: '10px 0', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
          {blunderRates.map((rate: number, idx: number) => {
            const heightPct = (rate / maxRate) * 100;
            return (
              <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
                <div style={{ width: '100%', height: `${heightPct}%`, backgroundColor: 'var(--color-primary)', borderRadius: '4px 4px 0 0', opacity: 0.8 }} title={`Profile ${idx + 1}: ${rate.toFixed(1)}`} />
                <span style={{ fontSize: '10px', marginTop: '4px', opacity: 0.7 }}>{idx + 1}</span>
              </div>
            );
          })}
        </div>
        <p style={{ fontSize: '12px', opacity: 0.7, textAlign: 'center', marginTop: '8px' }}>Confirmed blunders per 100 moves</p>
      </div>

      <div className="glass-panel">
        <h3 className="gradient-text">Training Accuracy</h3>
        {training && Object.keys(training).length > 0 ? (
          <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '10px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                <th style={{ padding: '8px 4px' }}>Motif / Source</th>
                <th style={{ padding: '8px 4px' }}>Attempts</th>
                <th style={{ padding: '8px 4px' }}>Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(training).map(([key, data]: [string, any]) => {
                const total = data.correct + data.incorrect;
                const acc = total > 0 ? (data.correct / total) * 100 : 0;
                return (
                  <tr key={key} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                    <td style={{ padding: '8px 4px' }}>{key}</td>
                    <td style={{ padding: '8px 4px' }}>{total}</td>
                    <td style={{ padding: '8px 4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <span style={{ width: '40px' }}>{acc.toFixed(0)}%</span>
                        <div style={{ flex: 1, height: '6px', backgroundColor: 'rgba(255,255,255,0.1)', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${acc}%`, height: '100%', backgroundColor: acc > 75 ? 'var(--color-success)' : acc > 40 ? 'var(--color-warning)' : 'var(--color-danger)' }} />
                        </div>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        ) : (
          <p>No training data yet.</p>
        )}
      </div>

      <div className="glass-panel">
        <h3 className="gradient-text">Motif Blind Trajectories</h3>
        {motif_blind_series && Object.keys(motif_blind_series).length > 0 ? (
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '15px', marginTop: '15px' }}>
            {Object.entries(motif_blind_series).map(([motif, series]: [string, any]) => {
              const maxVal = Math.max(...(series as number[]), 1);
              return (
                <div key={motif} className="motif-trend-card" style={{ padding: '10px', backgroundColor: 'rgba(255,255,255,0.02)', borderRadius: '8px' }}>
                  <h4 style={{ margin: '0 0 10px 0', fontSize: '14px' }}>{motif}</h4>
                  <div style={{ display: 'flex', alignItems: 'flex-end', height: '40px', gap: '2px' }}>
                    {(series as number[]).map((val, idx) => (
                      <div key={idx} style={{ flex: 1, height: `${(val / maxVal) * 100}%`, backgroundColor: 'var(--color-secondary)', opacity: 0.7, borderRadius: '1px' }} title={`P${idx + 1}: ${val}`} />
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p>No motif blind series data.</p>
        )}
      </div>
    </div>
  );
}
