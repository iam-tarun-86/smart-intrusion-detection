import { useEffect, useState, useRef } from 'react';

function AlertPanel() {
    const [alerts, setAlerts] = useState([]);
    const [connected, setConnected] = useState(false);
    const wsRef = useRef(null);

    useEffect(() => {
        let pingInterval;
        let reconnectDelay = 1000; // Start with 1s, exponential backoff
        let reconnectTimer = null;
        let isMounted = true;

        const connect = () => {
            if (!isMounted) return;

            // Clean up old socket
            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.close();
            }

            const ws = new WebSocket('ws://localhost:8000/ws');
            wsRef.current = ws;

            ws.onopen = () => {
                if (!isMounted) return;
                setConnected(true);
                reconnectDelay = 1000; // Reset backoff on success
                console.log('[WS] Connected');
            };

            ws.onmessage = (event) => {
                if (event.data === 'pong') return;

                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'intrusion_alert') {
                        setAlerts(prev => [data.data, ...prev].slice(0, 20));
                    }
                } catch (err) {
                    console.error('[WS] Parse error:', event.data);
                }
            };

            ws.onclose = () => {
                if (!isMounted) return;
                setConnected(false);
                console.log(`[WS] Disconnected, reconnecting in ${reconnectDelay}ms...`);

                // Exponential backoff: 1s, 2s, 4s, 8s, max 30s
                reconnectTimer = setTimeout(() => {
                    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
                    connect();
                }, reconnectDelay);
            };

            ws.onerror = (err) => {
                console.error('[WS] Error:', err);
                // Don't reconnect here — onclose will handle it
            };

            // Keepalive ping every 25s
            pingInterval = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send('ping');
                }
            }, 25000);
        };

        // Delay first connection by 500ms to let backend settle
        const initialTimer = setTimeout(connect, 500);

        return () => {
            isMounted = false;
            clearInterval(pingInterval);
            clearTimeout(reconnectTimer);
            clearTimeout(initialTimer);
            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.close();
            }
        };
    }, []);

    return (
        <div className="alert-panel">
            <h2>Real-Time Alerts</h2>
            <div className={`connection-status ${connected ? 'connected' : 'disconnected'}`}>
                {connected ? '🟢 Connected' : '🔴 Disconnected'}
            </div>
            <div className="alerts-list">
                {alerts.length === 0 ? (
                    <p className="no-alerts">No active intrusions</p>
                ) : (
                    alerts.map((alert, idx) => (
                        <div key={idx} className={`alert-card severity-${alert.severity}`}>
                            <div className="alert-header">
                                <span className="alert-icon">🚨</span>
                                <span className="zone-name">{alert.zone_name}</span>
                                <span className="severity-badge">{alert.severity}</span>
                            </div>
                            <div className="alert-details">
                                <p>Confidence: {(alert.confidence * 100).toFixed(1)}%</p>
                                <p>Time: {new Date(alert.timestamp).toLocaleTimeString()}</p>
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    );
}

export default AlertPanel;