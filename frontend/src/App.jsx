import VideoFeed from './components/VideoFeed';
import AlertPanel from './components/AlertPanel';
import LogsTable from './components/LogsTable';
import './App.css';

function App() {
  return (
    <div className="app">
      <header className="app-header">
        <h1>🔐 Smart Intrusion Detection System</h1>
        <p>Real-time monitoring dashboard</p>
      </header>

      <main className="dashboard">
        <div className="top-row">
          <VideoFeed />
          <AlertPanel />
        </div>
        <LogsTable />
      </main>
    </div>
  );
}

export default App;