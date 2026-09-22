import { useState, useEffect } from 'react';
import { diagnose, getJobStatus } from '../../api/training';
import './Training.css';

interface DiagnosePanelProps {
  onProfileReady: () => void;
}

export default function DiagnosePanel({ onProfileReady }: DiagnosePanelProps) {
  const [pgn, setPgn] = useState('');
  const [playerName, setPlayerName] = useState('');
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await diagnose(pgn, playerName);
      setJobId(res.job_id);
    } catch (err: any) {
      setError(err.message || 'Failed to start diagnosis');
      setLoading(false);
    }
  };

  useEffect(() => {
    let interval: any;
    if (jobId) {
      interval = setInterval(async () => {
        try {
          const job = await getJobStatus(jobId);
          if (job.status === 'done') {
            clearInterval(interval);
            setLoading(false);
            setJobId(null);
            onProfileReady();
          } else if (job.status === 'error') {
            clearInterval(interval);
            setError(job.error || 'Job failed');
            setLoading(false);
            setJobId(null);
          } else {
            setProgress(job.progress);
          }
        } catch (err: any) {
          console.error(err);
        }
      }, 1000);
    }
    return () => clearInterval(interval);
  }, [jobId, onProfileReady]);

  return (
    <div className="glass-panel diagnose-panel">
      <h2 className="gradient-text">New Diagnosis</h2>
      <div className="form-group">
        <label>Player Name to Analyze</label>
        <input 
          type="text" 
          value={playerName} 
          onChange={e => setPlayerName(e.target.value)} 
          placeholder="Your name exactly as it appears in the PGN headers"
          className="glass-input"
        />
      </div>
      <div className="form-group">
        <label>PGN Data</label>
        <textarea 
          rows={10} 
          value={pgn} 
          onChange={e => setPgn(e.target.value)} 
          placeholder="Paste PGN here..."
          className="glass-input"
        />
      </div>
      
      {error && <div className="error-msg">{error}</div>}
      
      <button 
        onClick={handleStart} 
        disabled={loading || !pgn || !playerName}
        className="glass-btn primary"
      >
        {loading ? 'Diagnosing...' : 'Start Diagnosis'}
      </button>

      {loading && progress && (
        <div className="progress-container">
          <div className="progress-stats">
            <span>Stage A: {progress.stage_a_done}/{progress.total}</span>
            <span>Flagged: {progress.flagged}</span>
            <span>Stage B: {progress.stage_b_done}/{progress.flagged}</span>
            {progress.stage_steer_done != null && (
              <span>TS2 Steer: {progress.stage_steer_done}</span>
            )}
          </div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${(progress.stage_a_done / (progress.total || 1)) * 100}%` }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
