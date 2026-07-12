import { useEffect, useState, useRef } from 'react';

function AlertPanel() {
    const [alerts, setAlerts] = useState([]);
    const wsRef = useRef(null);

    useEffect(() => {
        let pingInterval;
        let reconnectDelay = 1000;
        let reconnectTimer = null;
        let isMounted = true;

        const connect = () => {
            if (!isMounted) return;

            if (wsRef.current) {
                wsRef.current.onclose = null;
                wsRef.current.onerror = null;
                wsRef.current.close();
            }

            const ws = new WebSocket('ws://localhost:8000/ws');
            wsRef.current = ws;

            ws.onopen = () => {
                if (!isMounted) return;
                reconnectDelay = 1000;
                console.log('[WS] Connected for toasts');
            };

            ws.onmessage = (event) => {
                if (event.data === 'pong') return;

                try {
                    const data = JSON.parse(event.data);
                    if (data.type === 'intrusion_alert') {
                        const alertData = data.data;
                        const newAlert = {
                            ...alertData,
                            toastId: Date.now() + Math.random()
                        };
                        setAlerts(prev => [newAlert, ...prev].slice(0, 5));

                        setTimeout(() => {
                            setAlerts(prev => prev.filter(a => a.toastId !== newAlert.toastId));
                        }, 5000);
                    }
                } catch (err) {
                    console.error('[WS] Parse error:', event.data);
                }
            };

            ws.onclose = () => {
                if (!isMounted) return;
                console.log(`[WS] Disconnected, reconnecting in ${reconnectDelay}ms...`);
                reconnectTimer = setTimeout(() => {
                    reconnectDelay = Math.min(reconnectDelay * 2, 30000);
                    connect();
                }, reconnectDelay);
            };

            ws.onerror = (err) => {
                console.error('[WS] Error:', err);
            };

            pingInterval = setInterval(() => {
                if (ws.readyState === WebSocket.OPEN) {
                    ws.send('ping');
                }
            }, 25000);
        };

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

    if (alerts.length === 0) return null;

    return (
        <div className="toast-container">
            {alerts.map((alert) => (
                <div key={alert.toastId} className={`toast severity-${alert.severity}`}>
                    <div className="alert-header">
                        <span className="alert-icon">🚨</span>
                        <span className="zone-name">{alert.zone_name}</span>
                        <span className="severity-badge">{alert.severity}</span>
                    </div>
                    <div className="alert-details">
                        <p>Camera: {alert.camera_id || 'Unknown'}</p>
                        <p>Person ID: #{alert.track_id || '?'}</p>
                        {alert.risk_score !== undefined && (
                            <p style={{ 
                                color: alert.risk_score >= 70 ? '#ef4444' : 
                                       alert.risk_score >= 40 ? '#f59e0b' : '#10b981',
                                fontWeight: 'bold'
                            }}>
                                🔴 RISK SCORE: {alert.risk_score}/100
                            </p>
                        )}
                        {alert.shirt_color && (
                            <p>Shirt: {alert.shirt_color.toUpperCase()}</p>
                        )}
                        <p>Confidence: {(alert.confidence * 100).toFixed(1)}%</p>
                    </div>
                </div>
            ))}
        </div>
    );
}

export default AlertPanel;