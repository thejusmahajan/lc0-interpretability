import './Training.css';
import { openingColorLabel } from './openingColor';
import WeaknessRanking from './WeaknessRanking';

interface ProfileReportProps {
  profile: any;
  onFindingClick: (finding: any) => void;
  onGenerateDrills: () => void;
}

export default function ProfileReport({ profile, onFindingClick, onGenerateDrills }: ProfileReportProps) {
  if (!profile) return <div className="glass-panel">No profile available.</div>;

  const agg = profile.aggregates || {};
  const motifs = Object.entries(agg.by_motif || {}).sort((a: any, b: any) => b[1].blind - a[1].blind);
  const openings = Object.entries(agg.by_opening || {}).sort((a: any, b: any) => b[1].blind_rate - a[1].blind_rate);
  const concepts = Object.entries(agg.by_concept || {}).sort((a: any, b: any) => b[1].missed - a[1].missed);

  const steerFindings: any[] = profile.steer_findings || [];
  const steerSummaryEntries = Object.entries(profile.steer_summary || {}).sort(
    (a: any, b: any) => ((b[1].sharp_moves ?? b[1].tal_moves) || 0) - ((a[1].sharp_moves ?? a[1].tal_moves) || 0)
  );
  const sharpCandidates = steerFindings.filter((sf: any) => sf.had_sharp_move ?? sf.had_tal_move);

  return (
    <div className="profile-report">
      <div className="profile-header glass-panel">
        <h2 className="gradient-text">Weakness Profile</h2>
        <div className="stats-row">
          <div className="stat-box">
            <span className="stat-label">Games Analyzed</span>
            <span className="stat-value">{profile.games_analyzed}</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Intuitive Blindness Rate</span>
            <span className="stat-value">{((agg.intuitive_blindness_rate || 0) * 100).toFixed(1)}%</span>
          </div>
          <div className="stat-box">
            <span className="stat-label">Attention Blindness Rate</span>
            <span className="stat-value">{((agg.attention_blindness_rate || 0) * 100).toFixed(1)}%</span>
          </div>
          {steerFindings.length > 0 && (
            <div className="stat-box">
              <span className="stat-label">Tactical Steering</span>
              <span className="stat-value">{steerFindings.length} <small className="dim">({sharpCandidates.length} sharp)</small></span>
            </div>
          )}
        </div>
        <button className="glass-btn primary" onClick={onGenerateDrills}>Generate Drills</button>
      </div>

      <div className="profile-grid">
        <WeaknessRanking />
        <div className="glass-panel">
          <h3>Top Motifs Missed</h3>
          <table className="glass-table">
            <thead>
              <tr><th>Motif</th><th>Blind</th><th>Missed</th></tr>
            </thead>
            <tbody>
              {motifs.slice(0, 5).map(([m, stats]: any) => (
                <tr key={m}>
                  <td>{m}</td>
                  <td>{stats.blind || 0}</td>
                  <td>{stats.missed || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div className="glass-panel">
          <h3>Top Openings</h3>
          <table className="glass-table">
            <thead>
              <tr><th>ECO</th><th>Color</th><th>Moves</th><th>Blind Rate</th></tr>
            </thead>
            <tbody>
              {openings.slice(0, 5).map(([eco, stats]: any) => (
                <tr key={eco}>
                  <td>{eco}</td>
                  <td>{openingColorLabel(stats)}</td>
                  <td>{stats.moves || 0}</td>
                  <td>{((stats.blind_rate || 0) * 100).toFixed(1)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="glass-panel">
          <h3>Top Concepts</h3>
          <table className="glass-table">
            <thead>
              <tr><th>Concept</th><th>Missed</th></tr>
            </thead>
            <tbody>
              {concepts.slice(0, 5).map(([concept, stats]: any) => (
                <tr key={concept}>
                  <td>{concept}</td>
                  <td>{stats.missed || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {(steerFindings.length > 0 || steerSummaryEntries.length > 0) && (
        <div className="glass-panel steer-section" data-testid="steer-section" style={{ marginTop: '1.5rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <h3 className="gradient-text" style={{ margin: 0 }}>Tactical Steering (TS2)</h3>
            <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
              <span className="stat-pill" style={{ background: 'rgba(255, 150, 0, 0.15)', border: '1px solid orange', color: 'orange' }}>
                <strong>{steerFindings.length}</strong> Steer Positions
              </span>
              <span className="stat-pill" style={{ background: 'rgba(239, 68, 68, 0.15)', border: '1px solid var(--color-danger)', color: '#f87171' }}>
                <strong>{sharpCandidates.length}</strong> Sharp Candidates
              </span>
              {profile.steer_budget_exhausted && (
                <span className="tag" style={{ backgroundColor: 'var(--color-warning)', color: '#000', fontWeight: 600 }}>
                  Budget Exhausted
                </span>
              )}
            </div>
          </div>

          {steerSummaryEntries.length > 0 && (
            <div style={{ marginBottom: '1.25rem' }}>
              <h4 style={{ color: '#94a3b8', margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>Steering Summary by Opening</h4>
              <table className="glass-table" data-testid="steer-summary-table">
                <thead>
                  <tr><th>ECO</th><th>Moves</th><th>Sharp Moves</th><th>Mean Sharpness</th></tr>
                </thead>
                <tbody>
                  {steerSummaryEntries.slice(0, 6).map(([eco, st]: any) => (
                    <tr key={eco}>
                      <td><strong>{eco}</strong></td>
                      <td>{st.moves || 0}</td>
                      <td>{st.sharp_moves ?? st.tal_moves ?? 0}</td>
                      <td>{(st.mean_complexity || 0).toFixed(3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {steerFindings.length > 0 && (
            <div>
              <h4 style={{ color: '#94a3b8', margin: '0 0 0.5rem 0', fontSize: '0.9rem' }}>
                Top Sharp Steer Candidates
              </h4>
              <div className="findings-grid" data-testid="steer-findings-grid">
                {(sharpCandidates.length > 0 ? sharpCandidates : steerFindings).slice(0, 8).map((sf: any) => {
                  const isSharp = sf.had_sharp_move ?? sf.had_tal_move;
                  const moveNum = sf.move_number || Math.ceil((sf.ply || 1) / 2);
                  const playedText = sf.played?.san || sf.played?.uci || 'N/A';
                  const steerText = sf.steer?.san || sf.steer?.uci || sf.best?.san || sf.best?.uci || 'N/A';
                  const compVal = sf.steer?.complexity ?? sf.best?.complexity ?? 0;
                  return (
                    <div
                      key={sf.id}
                      className="finding-card glass-card steer-card"
                      data-testid={`steer-card-${sf.id}`}
                      style={{ borderLeft: isSharp ? '3px solid #f87171' : '3px solid orange' }}
                      onClick={() => onFindingClick({
                        ...sf,
                        move_number: moveNum,
                        severity: isSharp ? 'sharp' : 'steering',
                        played: sf.played,
                        best: sf.steer || sf.best,
                        user_color: sf.user_color || (sf.ply % 2 === 1 ? 'white' : 'black'),
                      })}
                    >
                      <div className="finding-header">
                        <span className="move-number">Move {moveNum} ({sf.opening?.eco || '???'})</span>
                        {isSharp ? (
                          <span className="severity blunder" style={{ background: 'rgba(239, 68, 68, 0.2)', color: '#f87171' }}>
                            ⚡ Sharp Move
                          </span>
                        ) : (
                          <span className="severity warning" style={{ background: 'rgba(255, 165, 0, 0.2)', color: 'orange' }}>
                            Steer
                          </span>
                        )}
                      </div>
                      <div className="finding-details">
                        <p><strong>Played:</strong> {playedText}</p>
                        <p><strong>Steer Line:</strong> {steerText}</p>
                        {sf.eval_loss_cp != null && (
                          <p className="swing-cp">Eval Loss: {(sf.eval_loss_cp / 100).toFixed(2)}</p>
                        )}
                        <div className="tags" style={{ marginTop: '4px' }}>
                          <span className="tag" style={{ background: 'rgba(255, 255, 255, 0.08)' }}>
                            Sharpness: {compVal.toFixed(2)}
                          </span>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}

      <div className="glass-panel findings-list">
        <h3>Notable Findings</h3>
        <div className="findings-grid">
          {profile.findings?.map((f: any) => (
            <div key={f.id} className="finding-card glass-card" onClick={() => onFindingClick(f)}>
              <div className="finding-header">
                <span className="move-number">Move {f.move_number}</span>
                <span className={`severity ${f.severity}`}>{f.severity}</span>
              </div>
              <div className="finding-details">
                <p><strong>Played:</strong> {f.played?.san || f.played?.uci || 'N/A'} {f.played?.p != null && <span className="dim">({(f.played.p * 100).toFixed(1)}%)</span>}</p>
                <p><strong>Best:</strong> {f.best?.san || f.best?.uci || 'N/A'} {f.best?.p != null && <span className="dim">({(f.best.p * 100).toFixed(1)}%)</span>}</p>
                {f.confirmation?.swing_cp != null && (
                  <p className="swing-cp">Swing: {(f.confirmation.swing_cp / 100).toFixed(2)}</p>
                )}
                {f.motifs?.length > 0 && (
                  <div className="tags">
                    {f.motifs.map((m: string) => <span key={m} className="tag">{m}</span>)}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
