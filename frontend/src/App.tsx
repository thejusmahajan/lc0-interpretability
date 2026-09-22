import { useState } from 'react';
import './App.css'
import PgnViewer from './components/PgnViewer'
import TrainingTab from './components/Training/TrainingTab'

function App() {
  const [activeTab, setActiveTab] = useState<'analysis' | 'training'>('analysis');

  return (
    <div className="app-layout">
      <header className="app-header">
        <h1 className="logo">
          Chess Speak <span className="highlight">Out Loud</span>
        </h1>
        <div className="main-tabs">
          <button 
            className={`tab-btn ${activeTab === 'analysis' ? 'active' : ''}`}
            onClick={() => setActiveTab('analysis')}
          >
            Analysis Mode
          </button>
          <button 
            className={`tab-btn ${activeTab === 'training' ? 'active' : ''}`}
            onClick={() => setActiveTab('training')}
          >
            Training Mode
          </button>
        </div>
      </header>
      
      <main className="main-content">
        {activeTab === 'analysis' ? <PgnViewer /> : <TrainingTab />}
      </main>
    </div>
  )
}

export default App
