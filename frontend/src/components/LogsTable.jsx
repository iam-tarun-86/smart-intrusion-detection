import { useEffect, useState } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';

function LogsTable({ compact = false }) {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);
    const { isAdmin } = useAuth();

    const fetchLogs = async () => {
        try {
            const limit = compact ? 10 : 50;
            const res = await axios.get(`http://localhost:8000/alerts?limit=${limit}`);
            setLogs(res.data);
        } catch (err) {
            console.error('[API Error]', err.message);
        } finally {
            setLoading(false);
        }
    };

    const resolveAlert = async (id) => {
        try {
            await axios.post(`http://localhost:8000/alerts/${id}/resolve`);
            fetchLogs();
        } catch (err) {
            console.error('[Resolve Error]', err.message);
        }
    };

    const clearLogs = async () => {
        if (!window.confirm('⚠️ Are you sure? This will delete ALL event logs permanently.')) return;
        try {
            await axios.delete('http://localhost:8000/alerts/all');
            fetchLogs();
        } catch (err) {
            alert(err.response?.data?.detail || 'Failed to clear logs');
        }
    };

    useEffect(() => {
        fetchLogs();
        const interval = setInterval(fetchLogs, 5000);
        return () => clearInterval(interval);
    }, [compact]);

    if (loading) return <div className="loading">Loading logs...</div>;

    if (logs.length === 0) {
        return <p className="no-logs">No events recorded yet</p>;
    }

    return (
        <div className={`logs-table ${compact ? 'compact' : 'full'}`}>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Time</th>
                        <th>Camera</th>
                        <th>Zone</th>
                        <th>Severity</th>
                        <th>Confidence</th>
                        <th>Status</th>
                        {!compact && <th>Action</th>}
                    </tr>
                </thead>
                <tbody>
                    {logs.map(log => (
                        <tr key={log.id} className={log.resolved ? 'resolved' : 'unresolved'}>
                            <td>{log.id}</td>
                            <td>{new Date(log.timestamp).toLocaleString()}</td>
                            <td>{log.camera_id?.toUpperCase() || 'Unknown'}</td>
                            <td>{log.zone_name}</td>
                            <td>
                                <span className={`badge severity-${log.severity}`}>{log.severity}</span>
                            </td>
                            <td>{(log.confidence * 100).toFixed(1)}%</td>
                            <td>{log.resolved ? '✅ Resolved' : '⚠️ Active'}</td>
                            {!compact && (
                                <td>
                                    {!log.resolved && (
                                        <button onClick={() => resolveAlert(log.id)} className="resolve-btn">
                                            Resolve
                                        </button>
                                    )}
                                </td>
                            )}
                        </tr>
                    ))}
                </tbody>
            </table>
            {compact && logs.length >= 5 && (
                <p className="more-hint">⛶ Full Screen for more logs</p>
            )}
            {!compact && isAdmin() && (
                <div style={{ marginTop: '1rem', textAlign: 'right' }}>
                    <button onClick={clearLogs} className="clear-btn">
                        🗑️ Clear All Logs
                    </button>
                </div>
            )}
        </div>
    );
}

export default LogsTable;