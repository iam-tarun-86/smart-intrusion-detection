import { useState, useEffect } from 'react';
import { AuthProvider, useAuth } from './context/AuthContext';
import VideoFeed from './components/VideoFeed';
import AlertPanel from './components/AlertPanel';
import LogsTable from './components/LogsTable';
import Login from './components/Login';
import axios from 'axios';
import './App.css';

function Dashboard() {
  const [viewMode, setViewMode] = useState('split');
  const [focusedCamera, setFocusedCamera] = useState(null);
  const [logsFullscreen, setLogsFullscreen] = useState(false);
  const [cameras, setCameras] = useState([]);
  const [activeCams, setActiveCams] = useState(['cam1', 'cam2']);
  const { user, logout } = useAuth();

  useEffect(() => {
    axios.get('http://localhost:8000/cameras').then(res => {
      setCameras(res.data);
      // Default to first 2 cameras if not set
      if (activeCams.length === 0 && res.data.length > 0) {
        setActiveCams(res.data.slice(0, 2).map(c => c.id));
      }
    });
  }, []);

  const enterFocus = (cameraId) => {
    setFocusedCamera(cameraId);
    setViewMode('focus');
  };

  const backToSplit = () => {
    setViewMode('split');
    setFocusedCamera(null);
  };

  const toggleCam = (camId) => {
    setActiveCams(prev =>
      prev.includes(camId)
        ? prev.filter(c => c !== camId)
        : [...prev, camId]
    );
  };

  return (
    <div className="app">
      <div className="dash-status-bar">
        <div className="dash-status-left">
          <span className="status-dot online"></span>
          <span className="dash-status-text">SYSTEM ONLINE</span>
          <span className="dash-sep">|</span>
          <span className="dash-cam-status">{cameras.length} CAMERAS CONFIGURED</span>
        </div>
        <div className="dash-status-right">
          <span className="dash-user">👤 {user.username}</span>
          <span className={`dash-role ${user.role}`}>{user.role.toUpperCase()}</span>
          <button onClick={logout} className="dash-logout">DISCONNECT</button>
        </div>
      </div>

      <header className="dash-header">
        <div className="dash-header-left">
          <div className="dash-logo">
            <span className="logo-icon">🔐</span>
            <div>
              <h1>SMART INTRUSION DETECTION</h1>
              <p>REAL-TIME MONITORING DASHBOARD</p>
            </div>
          </div>
        </div>
        <div className="dash-header-right">
          <div className="cam-selector">
            {cameras.map(cam => (
              <button
                key={cam.id}
                className={`cam-toggle ${activeCams.includes(cam.id) ? 'active' : ''}`}
                onClick={() => toggleCam(cam.id)}
              >
                <span className={`cam-dot ${activeCams.includes(cam.id) ? 'on' : ''}`}></span>
                {cam.name}
              </button>
            ))}
          </div>
        </div>
      </header>

      <main className={`dashboard ${viewMode}`}>
        <AlertPanel />

        {logsFullscreen ? (
          <div className="logs-fullscreen fade-in">
            <div className="logs-header-bar">
              <button onClick={() => setLogsFullscreen(false)} className="back-btn">
                ← RETURN
              </button>
              <h2>EVENT LOGS</h2>
              <span className="log-count">FULL HISTORY</span>
            </div>
            <LogsTable compact={false} />
          </div>
        ) : viewMode === 'split' ? (
          <div className="split-layout fade-in">
            <div className="split-view">
              <div className="split-cameras" style={{
                display: 'grid',
                gridTemplateColumns: `repeat(${Math.min(activeCams.length, 2)}, 1fr)`,
                gap: '1rem'
              }}>
                {activeCams.map(camId => (
                  <VideoFeed
                    key={camId}
                    cameraId={camId}
                    isFocus={false}
                    onExpand={() => enterFocus(camId)}
                  />
                ))}
              </div>
            </div>
            <div className="logs-section">
              <div className="logs-header">
                <div className="section-title">
                  <span className="section-icon">📋</span>
                  <h2>EVENT LOGS</h2>
                </div>
                <button onClick={() => setLogsFullscreen(true)} className="fullscreen-btn">
                  ⛶ EXPAND
                </button>
              </div>
              <LogsTable compact={true} />
            </div>
          </div>
        ) : (
          <div className="focus-layout fade-in">
            <div className="focus-toolbar">
              <button onClick={backToSplit} className="back-btn">
                ← RETURN TO SPLIT VIEW
              </button>
              <span className="focus-cam-label">
                CAMERA: {focusedCamera?.toUpperCase()}
              </span>
            </div>
            <VideoFeed cameraId={focusedCamera} isFocus={true} />
          </div>
        )}
      </main>
    </div>
  );
}

function AppContent() {
  const { user, loading } = useAuth();

  if (loading) return (
    <div className="loading-screen">
      <div className="loader-radar">
        <div className="loader-sweep"></div>
      </div>
      <p>INITIALIZING SYSTEM...</p>
    </div>
  );

  if (!user) return <Login />;

  return <Dashboard />;
}

function App() {
  return (
    <AuthProvider>
      <AppContent />
    </AuthProvider>
  );
}

export default App;