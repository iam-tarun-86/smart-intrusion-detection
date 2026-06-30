function VideoFeed() {
  return (
    <div className="video-feed">
      <h2>Live Feed</h2>
      <div className="video-container">
        <img 
          src="http://localhost:8000/stream" 
          alt="Live Stream"
          className="stream-img"
        />
      </div>
    </div>
  );
}

export default VideoFeed;