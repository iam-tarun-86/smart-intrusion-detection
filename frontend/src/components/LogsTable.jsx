import { useEffect, useState } from 'react';
import axios from 'axios';

function LogsTable() {
    const [logs, setLogs] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchLogs = async () => {
        try {
            const res = await axios.get('http://localhost:8000/alerts?limit=50');
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

    useEffect(() => {
        fetchLogs();
        const interval = setInterval(fetchLogs, 5000);
        return () => clearInterval(interval);
    }, []);

    if (loading) return <div className="loading">Loading logs...</div>;

    return (
        <div className="logs-table">
            <h2>Event Logs</h2>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Time</th>
                        <th>Zone</th>
                        <th>Severity</th>
                        <th>Confidence</th>
                        <th>Status</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {logs.map(log => (
                        <tr key={log.id} className={log.resolved ? 'resolved' : 'unresolved'}>
                            <td>{log.id}</td>
                            <td>{new Date(log.timestamp).toLocaleString()}</td>
                            <td>{log.zone_name}</td>
                            <td>
                                <span className={`badge severity-${log.severity}`}>{log.severity}</span>
                            </td>
                            <td>{(log.confidence * 100).toFixed(1)}%</td>
                            <td>{log.resolved ? '✅ Resolved' : '⚠️ Active'}</td>
                            <td>
                                {!log.resolved && (
                                    <button onClick={() => resolveAlert(log.id)} className="resolve-btn">
                                        Resolve
                                    </button>
                                )}
                            </td>
                        </tr>
                    ))}
                </tbody>
            </table>
            {logs.length === 0 && <p className="no-logs">No events recorded yet</p>}
        </div>
    );
}

export default LogsTable;