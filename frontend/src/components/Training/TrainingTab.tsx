import { useState, useEffect } from 'react';
import DiagnosePanel from './DiagnosePanel';
import ProfileReport from './ProfileReport';
import DrillMode from './DrillMode';
import TrainingBoard from './TrainingBoard';
import ProgressPanel from './ProgressPanel';
import RepertoirePanel from './RepertoirePanel';
import UsualSuspects from './UsualSuspects';
import IntuitionDrill from './IntuitionDrill';
import SacDrill from './SacDrill';
import SharpOpenings from './SharpOpenings';
import PuzzleStreak from './PuzzleStreak';
import { getProfile, generateDrills, getDueDrills, getDrillsList, getTrends } from '../../api/training';
import './Training.css';

export default function TrainingTab() {
  const [view, setView] = useState<'diagnose' | 'profile' | 'usual_suspects' | 'drills' | 'progress' | 'saved_sets' | 'repertoire' | 'intuition' | 'sacrifices' | 'sharp_openings' | 'puzzle_streak'>('diagnose');
  const [profile, setProfile] = useState<any>(null);
  const [drillSetId, setDrillSetId] = useState<string | null>(null);
  const [reviewItems, setReviewItems] = useState<any[] | null>(null);
  const [selectedFinding, setSelectedFinding] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [drillError, setDrillError] = useState<string | null>(null);
  
  const [dueCount, setDueCount] = useState(0);
  const [trends, setTrends] = useState<any>(null);
  const [savedSetsList, setSavedSetsList] = useState<any[]>([]);

  const fetchProfile = async () => {
    try {
      const p = await getProfile();
      if (p) {
        setProfile(p);
        setView('profile');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const fetchSRS = async () => {
    try {
      const due = await getDueDrills();
      setDueCount(due.count);
    } catch (e) {
      console.error('Failed to fetch due drills', e);
    }
  };

  const fetchTrendsData = async () => {
    try {
      const t = await getTrends();
      setTrends(t);
    } catch (e) {
      console.error('Failed to fetch trends', e);
    }
  };

  const fetchSavedSets = async () => {
    try {
      const list = await getDrillsList();
      setSavedSetsList(list);
    } catch (e) {
      console.error('Failed to fetch saved sets', e);
    }
  };

  useEffect(() => {
    fetchProfile();
    fetchSRS();
    fetchTrendsData();
    fetchSavedSets();
  }, []);

  const handleReview = async () => {
    try {
      setLoading(true);
      const res = await getDueDrills();
      setReviewItems(res.due);
      setDrillSetId(null);
      setView('drills');
      setLoading(false);
    } catch (e) {
      console.error('Failed to start review', e);
      setLoading(false);
    }
  };

  const handleGenerateDrills = async () => {
    try {
      setLoading(true);
      setDrillError(null);
      const res = await generateDrills(5);
      setDrillSetId(res.id || res.set_id); // API contract returns {id: ...}
      setReviewItems(null);
      setView('drills');
      fetchSavedSets(); // refresh list
      setLoading(false);
    } catch (err: any) {
      console.error('Failed to generate drills', err);
      setDrillError(err.message || 'Failed to generate drills');
      setLoading(false);
    }
  };

  const handleLoadSet = (id: string) => {
    setDrillSetId(id);
    setReviewItems(null);
    setView('drills');
  };

  return (
    <div className="training-tab">
      <div className="training-nav glass-panel">
        <button 
          className={`glass-btn ${view === 'diagnose' ? 'active' : ''}`}
          onClick={() => setView('diagnose')}
        >
          Diagnose PGN
        </button>
        <button 
          className={`glass-btn ${view === 'profile' ? 'active' : ''}`}
          onClick={() => setView('profile')}
          disabled={!profile}
        >
          Weakness Profile
        </button>
        <button
          className={`glass-btn ${view === 'usual_suspects' ? 'active' : ''}`}
          onClick={() => setView('usual_suspects')}
        >
          Usual Suspects
        </button>
        <button
          className={`glass-btn ${view === 'saved_sets' ? 'active' : ''}`}
          onClick={() => setView('saved_sets')}
        >
          Training Drills
        </button>
        <button
          className={`glass-btn ${view === 'repertoire' ? 'active' : ''}`}
          onClick={() => setView('repertoire')}
        >
          Repertoire
        </button>
        <button
          className={`glass-btn ${view === 'intuition' ? 'active' : ''}`}
          onClick={() => setView('intuition')}
        >
          Train Intuition
        </button>
        <button
          className={`glass-btn ${view === 'sacrifices' ? 'active' : ''}`}
          onClick={() => setView('sacrifices')}
        >
          Train Sacrifices
        </button>
        <button
          className={`glass-btn ${view === 'sharp_openings' ? 'active' : ''}`}
          onClick={() => setView('sharp_openings')}
        >
          ⚔️ Sharp Openings
        </button>
        <button
          className={`glass-btn ${view === 'puzzle_streak' ? 'active' : ''}`}
          onClick={() => setView('puzzle_streak')}
        >
          🔥 Puzzle Streak
        </button>
        <button 
          className={`glass-btn ${view === 'drills' && reviewItems ? 'active' : ''}`}
          onClick={handleReview}
          disabled={dueCount === 0 || loading}
          style={dueCount > 0 ? { backgroundColor: 'rgba(255, 165, 0, 0.2)' } : {}}
        >
          {loading && !reviewItems ? 'Loading...' : `Review (${dueCount} due)`}
        </button>
        <button 
          className={`glass-btn ${view === 'progress' ? 'active' : ''}`}
          onClick={() => setView('progress')}
          disabled={!trends}
        >
          Progress
        </button>
        {drillError && <div className="error-msg" style={{ marginLeft: 'auto', color: 'var(--color-danger)' }}>{drillError}</div>}
      </div>

      <div className="training-content">
        {view === 'diagnose' && (
          <DiagnosePanel onProfileReady={() => { fetchProfile(); fetchTrendsData(); fetchSRS(); }} />
        )}

        {view === 'profile' && profile && (
          <div className="profile-view-layout">
            <ProfileReport 
              profile={profile} 
              onFindingClick={setSelectedFinding}
              onGenerateDrills={handleGenerateDrills}
            />
            {selectedFinding && (
              <div className="finding-board-container glass-panel">
                <h3>Missed Opportunity</h3>
                <TrainingBoard 
                  fen={selectedFinding.fen_before}
                  orientation={selectedFinding.user_color}
                  interactive={false}
                  policy={[selectedFinding.best, selectedFinding.played].filter(Boolean)}
                  saliency={null}
                  hotSquares={selectedFinding.attention?.hot_squares || []}
                  blunderFlash={true}
                />
              </div>
            )}
          </div>
        )}

        {view === 'saved_sets' && (
          <div className="saved-sets-view glass-panel">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 className="gradient-text">Saved Drill Sets</h2>
              <button className="glass-btn primary" onClick={handleGenerateDrills} disabled={loading}>
                {loading ? 'Generating...' : 'Generate New Set'}
              </button>
            </div>
            
            {savedSetsList.length === 0 ? (
              <p>No saved drill sets. Generate one to start training!</p>
            ) : (
              <table style={{ width: '100%', borderCollapse: 'collapse', marginTop: '15px' }}>
                <thead>
                  <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)', textAlign: 'left' }}>
                    <th style={{ padding: '8px' }}>Created</th>
                    <th style={{ padding: '8px' }}>Size</th>
                    <th style={{ padding: '8px' }}>Sources</th>
                    <th style={{ padding: '8px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {savedSetsList.map((set: any) => (
                    <tr key={set.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                      <td style={{ padding: '8px' }}>{new Date(set.created).toLocaleString()}</td>
                      <td style={{ padding: '8px' }}>{set.drills?.length || 0} drills</td>
                      <td style={{ padding: '8px' }}>
                        {Array.from(new Set(set.drills?.map((d:any) => d.source))).join(', ')}
                      </td>
                      <td style={{ padding: '8px' }}>
                        <button className="glass-btn" onClick={() => handleLoadSet(set.id)}>Load</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}

        {view === 'progress' && trends && (
          <ProgressPanel trends={trends} />
        )}

        {view === 'repertoire' && <RepertoirePanel />}

        {view === 'usual_suspects' && (
          <UsualSuspects
            onDeckBuilt={(id) => {
              setDrillSetId(id);
              setReviewItems(null);
              setView('drills');
              fetchSavedSets();
            }}
          />
        )}

        {view === 'intuition' && <IntuitionDrill />}

        {view === 'sacrifices' && <SacDrill />}

        {view === 'sharp_openings' && <SharpOpenings />}

        {view === 'puzzle_streak' && <PuzzleStreak onExit={() => setView('profile')} />}

        {view === 'drills' && (drillSetId || reviewItems) && (
          <DrillMode setId={drillSetId || undefined} dueItems={reviewItems || undefined} onExit={() => { setView('profile'); fetchSRS(); fetchTrendsData(); }} />
        )}
      </div>
    </div>
  );
}
