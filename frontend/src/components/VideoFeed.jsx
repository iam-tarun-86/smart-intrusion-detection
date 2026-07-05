import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { useAuth } from '../context/AuthContext';  // ADD THIS IMPORT

function VideoFeed({ cameraId, isFocus, onExpand }) {
  const { isAdmin } = useAuth();  // ADD THIS
  const [savedZones, setSavedZones] = useState([]);
  const [isEditing, setIsEditing] = useState(false);
  const [points, setPoints] = useState([]);
  const [zoneName, setZoneName] = useState('');
  const [severity, setSeverity] = useState('high');
  const [cameraInfo, setCameraInfo] = useState(null);
  const canvasRef = useRef(null);

  // Load camera info and zones
  useEffect(() => {
    axios.get('http://localhost:8000/cameras')
      .then(res => {
        const cam = res.data.find(c => c.id === cameraId);
        setCameraInfo(cam);
      });

    axios.get(`http://localhost:8000/zones/${cameraId}`)
      .then(res => setSavedZones(res.data))
      .catch(() => setSavedZones([]));
  }, [cameraId]);

  // Handle canvas click for zone drawing
  const handleCanvasClick = useCallback((e) => {
    if (!isEditing) return;

    const canvas = canvasRef.current;
    const rect = canvas.getBoundingClientRect();
    const scaleX = canvas.width / rect.width;
    const scaleY = canvas.height / rect.height;

    const x = Math.round((e.clientX - rect.left) * scaleX);
    const y = Math.round((e.clientY - rect.top) * scaleY);

    setPoints(prev => [...prev, [x, y]]);
  }, [isEditing]);

  const saveZone = async () => {
    if (!zoneName.trim() || points.length < 3) {
      alert('Need name + at least 3 points');
      return;
    }

    const newZone = {
      name: zoneName,
      points: points,
      color: severity === 'high' ? [0, 0, 255] : severity === 'medium' ? [255, 165, 0] : [0, 255, 0],
      severity: severity
    };

    const existingZones = savedZones.map(z => ({
      name: z.name,
      points: z.points,
      color: z.color,
      severity: z.severity
    }));

    try {
      await axios.post(`http://localhost:8000/zones/${cameraId}`, [...existingZones, newZone]);
      setSavedZones(prev => [...prev, newZone]);
      setPoints([]);
      setZoneName('');
      setIsEditing(false);
      alert('Zone saved! It will apply in ~30 seconds.');
    } catch (err) {
      alert('Failed to save zone');
    }
  };

  // Draw canvas overlay
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // Draw saved zones
    savedZones.forEach(zone => {
      ctx.strokeStyle = `rgb(${zone.color.join(',')})`;
      ctx.lineWidth = 3;
      ctx.fillStyle = `rgba(${zone.color.join(',')}, 0.1)`;

      ctx.beginPath();
      ctx.moveTo(zone.points[0][0], zone.points[0][1]);
      zone.points.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
      ctx.closePath();
      ctx.fill();
      ctx.stroke();

      ctx.fillStyle = `rgb(${zone.color.join(',')})`;
      ctx.font = '16px Arial';
      const centerX = zone.points.reduce((sum, p) => sum + p[0], 0) / zone.points.length;
      const centerY = zone.points.reduce((sum, p) => sum + p[1], 0) / zone.points.length;
      ctx.fillText(zone.name, centerX - 30, centerY);
    });

    // Draw editing points
    if (isEditing && points.length > 0) {
      ctx.strokeStyle = '#00ff00';
      ctx.lineWidth = 2;
      ctx.fillStyle = 'rgba(0, 255, 0, 0.2)';

      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      points.slice(1).forEach(p => ctx.lineTo(p[0], p[1]));
      ctx.stroke();

      points.forEach((p, i) => {
        ctx.fillStyle = '#00ff00';
        ctx.beginPath();
        ctx.arc(p[0], p[1], 5, 0, 2 * Math.PI);
        ctx.fill();
        ctx.fillStyle = '#fff';
        ctx.font = '12px Arial';
        ctx.fillText(i + 1, p[0] + 8, p[1] - 8);
      });
    }
  }, [savedZones, points, isEditing]);

  return (
    <div className={`video-feed ${isFocus ? 'focus-mode' : 'split-mode'}`}>
      <div className="video-header">
        <div className="camera-title">
          <span className="live-badge">LIVE</span>
          <h3>{cameraInfo?.name || cameraId}</h3>
        </div>
        {!isFocus && (
          <button onClick={onExpand} className="expand-btn">
            ⛶
          </button>
        )}
      </div>

      {isFocus && isAdmin() && (
        <div className="zone-controls">
          {!isEditing ? (
            <button onClick={() => setIsEditing(true)} className="edit-btn">
              ✏️ Draw Zone
            </button>
          ) : (
            <div className="edit-panel">
              <input
                type="text"
                placeholder="Zone name"
                value={zoneName}
                onChange={(e) => setZoneName(e.target.value)}
                className="zone-input"
              />
              <select value={severity} onChange={(e) => setSeverity(e.target.value)} className="severity-select">
                <option value="high">High</option>
                <option value="medium">Medium</option>
                <option value="low">Low</option>
              </select>
              <span className="point-count">{points.length} pts</span>
              <button onClick={saveZone} className="save-btn" disabled={points.length < 3}>
                💾 Save
              </button>
              <button onClick={() => { setPoints([]); setIsEditing(false); }} className="cancel-btn">
                ❌ Cancel
              </button>
            </div>
          )}
        </div>
      )}

      <div className="video-container" style={{ position: 'relative' }}>
        <img
          src={`http://localhost:8000/stream/${cameraId}`}
          alt={`Live Stream - ${cameraId}`}
          className="stream-img"
          style={{ position: 'absolute', top: 0, left: 0, zIndex: 1, width: '100%', height: '100%' }}
        />
        <canvas
          ref={canvasRef}
          width={768}
          height={432}
          onClick={handleCanvasClick}
          style={{
            position: 'absolute',
            top: 0,
            left: 0,
            zIndex: 2,
            width: '100%',
            height: '100%',
            cursor: isEditing ? 'crosshair' : 'default',
            pointerEvents: isEditing ? 'auto' : 'none'
          }}
        />
      </div>
    </div>
  );
}

export default VideoFeed;