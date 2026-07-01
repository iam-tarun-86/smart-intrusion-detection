import { useState, useEffect } from 'react';
import axios from 'axios';

function VideoFeed() {
  const [cameras, setCameras] = useState([]);
  const [selectedCamera, setSelectedCamera] = useState('cam1');

  useEffect(() => {
    axios.get('http://localhost:8000/cameras')
      .then(res => {
        setCameras(res.data);
        if (res.data.length > 0 && !selectedCamera) {
          setSelectedCamera(res.data[0].id);
        }
      })
      .catch(err => console.error('[Cameras Error]', err));
  }, []);

  return (
    <div className="video-feed">
      <div className="video-header">
        <h2>Live Feed</h2>
        <select
          value={selectedCamera}
          onChange={(e) => setSelectedCamera(e.target.value)}
          className="camera-select"
        >
          {cameras.map(cam => (
            <option key={cam.id} value={cam.id}>
              {cam.name} ({cam.id})
            </option>
          ))}
        </select>
      </div>
      <div className="video-container">
        {selectedCamera ? (
          <img
            src={`http://localhost:8000/stream/${selectedCamera}`}
            alt={`Live Stream - ${selectedCamera}`}
            className="stream-img"
          />
        ) : (
          <p className="no-stream">Select a camera</p>
        )}
      </div>
    </div>
  );
}

export default VideoFeed;