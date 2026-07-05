import { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';

function Login() {
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const [currentTime, setCurrentTime] = useState(new Date());
    const [scanLine, setScanLine] = useState(0);
    const { login } = useAuth();

    useEffect(() => {
        const timer = setInterval(() => setCurrentTime(new Date()), 1000);
        return () => clearInterval(timer);
    }, []);

    useEffect(() => {
        const anim = setInterval(() => {
            setScanLine(prev => (prev + 1) % 100);
        }, 50);
        return () => clearInterval(anim);
    }, []);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setError('');
        setIsLoading(true);
        try {
            await login(username, password);
        } catch (err) {
            setError('ACCESS DENIED — INVALID CREDENTIALS');
        } finally {
            setIsLoading(false);
        }
    };

    const formatTime = (d) => d.toLocaleTimeString('en-US', { hour12: false });
    const formatDate = (d) => d.toLocaleDateString('en-US', {
        weekday: 'short', year: 'numeric', month: 'short', day: '2-digit'
    });

    return (
        <div className="command-login">
            {/* Scanning overlay */}
            <div className="scan-overlay" style={{ top: `${scanLine}%` }}></div>

            {/* Grid background */}
            <div className="grid-bg"></div>

            {/* Corner brackets */}
            <div className="corner corner-tl"></div>
            <div className="corner corner-tr"></div>
            <div className="corner corner-bl"></div>
            <div className="corner corner-br"></div>

            <div className="command-container">
                {/* Header status bar */}
                <div className="status-bar">
                    <div className="status-left">
                        <span className="status-dot online"></span>
                        <span className="status-text">SYSTEM ONLINE</span>
                        <span className="separator">|</span>
                        <span className="security-level">SECURITY LEVEL: MAXIMUM</span>
                    </div>
                    <div className="status-right">
                        <span>{formatDate(currentTime)}</span>
                        <span className="separator">|</span>
                        <span className="clock">{formatTime(currentTime)}</span>
                    </div>
                </div>

                {/* Main content */}
                <div className="command-body">
                    {/* Left panel - system info */}
                    <div className="system-panel">
                        <div className="panel-header">SYSTEM DIAGNOSTICS</div>
                        <div className="diag-line">
                            <span className="diag-label">DETECTION ENGINE</span>
                            <span className="diag-value ok">ACTIVE</span>
                        </div>
                        <div className="diag-line">
                            <span className="diag-label">CAMERA FEEDS</span>
                            <span className="diag-value ok">2/2 ONLINE</span>
                        </div>
                        <div className="diag-line">
                            <span className="diag-label">NEURAL NETWORK</span>
                            <span className="diag-value ok">YOLOv8 READY</span>
                        </div>
                        <div className="diag-line">
                            <span className="diag-label">DATABASE</span>
                            <span className="diag-value ok">CONNECTED</span>
                        </div>
                        <div className="diag-line">
                            <span className="diag-label">ALERT QUEUE</span>
                            <span className="diag-value ok">CLEAR</span>
                        </div>

                        <div className="panel-header" style={{ marginTop: '2rem' }}>NETWORK STATUS</div>
                        <div className="network-viz">
                            {[...Array(20)].map((_, i) => (
                                <div
                                    key={i}
                                    className="net-bar"
                                    style={{
                                        height: `${Math.random() * 40 + 10}px`,
                                        animationDelay: `${i * 0.1}s`
                                    }}
                                ></div>
                            ))}
                        </div>
                    </div>

                    {/* Center - login form */}
                    <div className="login-center">
                        <div className="radar-container">
                            <div className="radar">
                                <div className="radar-sweep"></div>
                                <div className="radar-ring r1"></div>
                                <div className="radar-ring r2"></div>
                                <div className="radar-ring r3"></div>
                                <div className="radar-dot"></div>
                            </div>
                        </div>

                        <div className="login-title-block">
                            <div className="title-line">
                                <span className="bracket">[</span>
                                <h1>SMART INTRUSION DETECTION</h1>
                                <span className="bracket">]</span>
                            </div>
                            <p className="subtitle">AUTHORIZED PERSONNEL ONLY</p>
                        </div>

                        {error && (
                            <div className="access-denied">
                                <span className="blink">⚠</span> {error}
                            </div>
                        )}

                        <form onSubmit={handleSubmit} className="command-form">
                            <div className="form-row">
                                <span className="prompt">&gt;</span>
                                <div className="input-wrap">
                                    <label>OPERATOR ID</label>
                                    <input
                                        type="text"
                                        value={username}
                                        onChange={(e) => setUsername(e.target.value)}
                                        placeholder="Enter operator ID"
                                        autoFocus
                                    />
                                </div>
                            </div>

                            <div className="form-row">
                                <span className="prompt">&gt;</span>
                                <div className="input-wrap">
                                    <label>ACCESS KEY</label>
                                    <input
                                        type="password"
                                        value={password}
                                        onChange={(e) => setPassword(e.target.value)}
                                        placeholder="Enter access key"
                                    />
                                </div>
                            </div>

                            <button
                                type="submit"
                                className={`command-btn ${isLoading ? 'processing' : ''}`}
                                disabled={isLoading}
                            >
                                {isLoading ? (
                                    <>
                                        <span className="btn-spinner"></span>
                                        AUTHENTICATING...
                                    </>
                                ) : (
                                    <>
                                        <span className="lock-icon">🔒</span>
                                        AUTHENTICATE
                                    </>
                                )}
                            </button>
                        </form>

                        <div className="terminal-hint">
                            <div className="term-line">
                                <span className="term-prompt">$</span>
                                <span className="term-cmd">systemctl status intrusion-detection</span>
                            </div>
                            <div className="term-line">
                                <span className="term-prompt">$</span>
                                <span className="term-cmd">active (running) since boot</span>
                            </div>
                        </div>
                    </div>

                    {/* Right panel - logs */}
                    <div className="logs-panel">
                        <div className="panel-header">EVENT LOG</div>
                        <div className="log-entries">
                            <div className="log-entry">
                                <span className="log-time">22:28:01</span>
                                <span className="log-type info">[INFO]</span>
                                <span>System initialized</span>
                            </div>
                            <div className="log-entry">
                                <span className="log-time">22:28:02</span>
                                <span className="log-type ok">[OK]</span>
                                <span>Camera cam1 connected</span>
                            </div>
                            <div className="log-entry">
                                <span className="log-time">22:28:02</span>
                                <span className="log-type ok">[OK]</span>
                                <span>Camera cam2 connected</span>
                            </div>
                            <div className="log-entry">
                                <span className="log-time">22:28:03</span>
                                <span className="log-type info">[INFO]</span>
                                <span>Zone configs loaded</span>
                            </div>
                            <div className="log-entry">
                                <span className="log-time">22:28:03</span>
                                <span className="log-type warn">[WARN]</span>
                                <span>Waiting for operator</span>
                            </div>
                        </div>
                    </div>
                </div>

                {/* Footer */}
                <div className="command-footer">
                    <span>SECURE CONNECTION • ENCRYPTED • v2.0.0</span>
                    <span className="footer-right">SMART INTRUSION DETECTION SYSTEM</span>
                </div>
            </div>
        </div>
    );
}

export default Login;