# 🔐 Smart Intrusion Detection System

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-v0.110-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![React](https://img.shields.io/badge/React-v18-20232a?logo=react&logoColor=61dafb)](https://react.dev/)
[![YOLOv8](https://img.shields.io/badge/Ultralytics-YOLOv8-FF6F00?logo=scikit-learn&logoColor=white)](https://docs.ultralytics.com/)
[![OpenCV](https://img.shields.io/badge/OpenCV-v4.9-5C3EE8?logo=opencv&logoColor=white)](https://opencv.org/)
[![SQLite](https://img.shields.io/badge/SQLite-v3-003B57?logo=sqlite&logoColor=white)](https://www.sqlite.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-v16-4169E1?logo=postgresql&logoColor=white)](https://www.postgresql.org/)

An enterprise-grade, real-time AI-powered physical security application combining computer vision, edge tracking, role-based operator dashboards, and instant telemetric alerts. The system utilizes **YOLOv8** for human detection, **ByteTrack** for persistent identity association, and **HSV/BGR analysis** for shirt-color uniform verification. 

Operators monitor live MJPEG camera streams, configure polygonal restricted zones on-the-fly, inspect real-time intrusion event logs, and receive instant alert notifications via **WebSockets** and **Telegram** channels.

---

## 🏗️ System Architecture

The following diagram illustrates the end-to-end data pipeline, from frame capture to real-time notification dispatch:

```mermaid
flowchart TD
    subgraph Capture["Video Ingestion Layer"]
        C1["Camera 1 (Server Room Video File)"] --> SM["Stream Manager"]
        C2["Camera 2 (Side Gate Video File)"] --> SM
        C3["Webcam / Direct RTSP Stream"] --> SM
    end

    subgraph CV_Engine["AI Computer Vision Engine"]
        SM -->|BGR Frame Buffer| PD["Person Detector (YOLOv8)"]
        PD -->|BBoxes & Confidence| BT["ByteTrack Multi-Object Tracker"]
        BT -->|Persistent Person IDs| CA["Color Analyzer (HSV Chest Profiler)"]
    end

    subgraph Logic["Intrusion Evaluation & Risk Engine"]
        CA -->|Shirt Color & Track ID| ZM["Zone Manager"]
        ZM -->|Point-in-Polygon Test| PI["Intrusion Checking & Cooldowns"]
        PI -->|Uniform Rules Check| RC["Risk Calculator (0-100 Score)"]
    end

    subgraph Storage["Persistence & Communication Layer"]
        RC -->|Intrusion Event Created| DB[("SQLite Database (intrusion.db)")]
        RC -->|Snapshot Saved| SN["Snapshots Directory"]
        RC -->|Broadcaster Queue| WSS["WebSocket Alert Dispatcher"]
        RC -->|Asynchronous Task| TG["Telegram Bot Notifier"]
    end

    subgraph Client["React Operator Dashboard"]
        WSS -->|JSON Toast payload| FE["React App (WebSockets)"]
        DB -->|REST API Pull| FE
        SN -->|Static Path Serving| FE
        FE -->|Operator Interaction| AP["Acknowledge & Resolve Actions"]
        AP -->|POST Request| DB
    end

    style Capture fill:#1a1c23,stroke:#3b82f6,stroke-width:2px,color:#fff
    style CV_Engine fill:#1e1e38,stroke:#a855f7,stroke-width:2px,color:#fff
    style Logic fill:#2d1b33,stroke:#ec4899,stroke-width:2px,color:#fff
    style Storage fill:#152b22,stroke:#10b981,stroke-width:2px,color:#fff
    style Client fill:#252525,stroke:#eab308,stroke-width:2px,color:#fff
```

---

## ⚡ Core Features Deep-Dive

### 1. Persistent Tracking with ByteTrack
Instead of triggering an alert on every frame, the system integrates a custom **ByteTrack IoU-based tracking algorithm** ([ByteTrack Tracker](file:///home/tarun/smart-intrusion-detection/backend/detection/detector.py#L12-L121)). This assigns a persistent `track_id` to each individual:
* **Cooldown Buffer**: Tracks are kept alive in memory for up to 30 frames if temporarily obstructed.
* **Redundant Alert Prevention**: Operators receive a single alert sequence rather than frame-by-frame spam.
* **Dwell Time Tracking**: Tracks the precise duration of time (seconds) a person has spent in the restricted zone.

### 2. HSV-Based Uniform Compliance Verification
Authorized personnel can be dynamically filtered by their clothing color. The system crops the chest region of detected bounding boxes (excluding face and legs) and runs HSV analysis:
* **Brightness-Based Fast Checks**: Instantly handles very bright white (parking lot lights) and dark/black clothing.
* **Mask Matching**: Evaluates color density using custom HSV range thresholds for `blue`, `white`, `red`, `green`, `black`, `yellow`, and `orange`.
* **Dynamic Uniform Rules**: Different cameras enforce different rules (e.g., `cam1` restricts all color shirts except blue; `cam2` allows blue and white).

### 3. Dynamic Polygon Zone Drawing
Operators can customize security zones directly on the dashboard:
* Draw custom polygons on the live canvas.
* Set security levels (`high`, `medium`, `low`) which impact visual borders, styling, and the overall risk score.
* Zone boundaries are written to configuration JSON files and loaded dynamically by the backend without server restarts.

### 4. Intelligent Multi-Factored Risk Engine
The system calculates a `risk_score` (0-100) for every detected intrusion event ([Risk Calculator](file:///home/tarun/smart-intrusion-detection/backend/detection/zones.py#L146-L183)):

| Dimension | Range | Criteria |
| :--- | :---: | :--- |
| **Detection Confidence** | 0 - 30 pts | Directly scaled based on YOLOv8 confidence metrics. |
| **Zone Dwelling Duration** | 0 - 30 pts | Scaled linearly, capping at max score after 60 seconds of zone residence. |
| **Zone Sensitivity** | 0 - 20 pts | Server Room (20), Restricted Area (18), Storage Area (12), Parking Lot (8). |
| **Uniform Compliance** | 0 - 20 pts | Unauthorized clothing color (20), Ambiguous / Unknown color (10). |

---

## 📁 Repository Structure

```
smart-intrusion-detection/
├── backend/
│   ├── db/
│   │   ├── database.py         # SQLAlchemy SQLite/PostgreSQL engine connection
│   │   └── models.py           # IntrusionEvent & User database models
│   ├── detection/
│   │   ├── color_analyzer.py   # HSV dominant shirt color analyzer
│   │   ├── detector.py         # YOLOv8 inference wrapper & ByteTrack implementation
│   │   └── zones.py            # Point-in-polygon checks, uniform filters & risk engine
│   ├── zone_configs/           # Stored JSON files representing polygon coordinates
│   ├── main.py                 # FastAPI server, WebSockets, API routers & auth controllers
│   ├── stream_manager.py       # Threaded multi-stream reader and config loader
│   ├── telegram_notifier.py    # Non-blocking async Telegram bot API client
│   ├── cameras.json            # Camera source registrations
│   └── requirements.txt        # Backend dependencies
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── AlertPanel.jsx  # Toast notifications with WebSocket hook
│   │   │   ├── LogsTable.jsx   # Interactive events list with search/resolve hooks
│   │   │   ├── VideoFeed.jsx   # Live stream viewer & canvas drawing editor
│   │   │   └── Login.jsx       # Diagnostic terminal dashboard interface
│   │   ├── context/
│   │   │   └── AuthContext.jsx # JWT session manager (Operator & Admin roles)
│   │   ├── App.jsx             # Main dashboard layout router
│   │   └── App.css             # Cybersecurity command CSS configurations
│   └── package.json            # Vite frontend dependencies
│
└── README.md                   # System Documentation
```

---

## 📊 API & Protocol Documentation

All REST APIs run on port `8000`. WebSocket channels route system events live.

### REST Endpoints

| Method | Endpoint | Required Role | Description |
| :---: | :--- | :---: | :--- |
| **GET** | `/` | Open | API version, features, and status. |
| **GET** | `/stream/{camera_id}` | Guard | Live MJPEG stream boundaries overlaying bboxes & zones. |
| **GET** | `/cameras` | Guard | Lists all registered cameras from configurations. |
| **POST** | `/cameras` | Admin | Registers a new camera channel. |
| **GET** | `/zones/{camera_id}` | Guard | Fetch polygon configurations for a given stream. |
| **POST** | `/zones/{camera_id}` | Admin | Saves new polygon coordinates for a given camera stream. |
| **DELETE** | `/zones/{camera_id}` | Admin | Clear all polygon zones associated with a camera channel. |
| **GET** | `/alerts` | Guard | Search/Fetch latest intrusion events (paginated). |
| **POST** | `/alerts/{event_id}/resolve` | Guard | Mark an active alert resolved. |
| **DELETE** | `/alerts/all` | Admin | Purge all logging databases. |
| **GET** | `/stats` | Guard | Fetch system counts (active alerts, camera totals). |
| **POST** | `/auth/login` | Open | JWT validation endpoint. Default logins configured below. |
| **GET** | `/auth/me` | Guard | Authenticates current user session details. |

### Real-Time WebSockets

* **URL**: `ws://localhost:8000/ws`
* **Protocol**: Sends `intrusion_alert` messages as JSON objects. Keeps connections alive with `ping`/`pong` handshakes.
* **Sample Payload**:
  ```json
  {
    "type": "intrusion_alert",
    "timestamp": "2026-07-12T04:55:00.123456",
    "data": {
      "id": 487,
      "timestamp": "2026-07-12T04:55:00.123456",
      "zone_name": "Server Room",
      "camera_id": "cam1",
      "severity": "high",
      "confidence": 0.92,
      "bbox": [152, 98, 380, 420],
      "track_id": 4,
      "shirt_color": "red",
      "authorized": false,
      "risk_score": 90,
      "duration_seconds": 15.4,
      "snapshot": "snapshots/cam1/event_20260712_045500.jpg"
    }
  }
  ```

---

## 🚀 Quick Start Guide

### Prerequisites
* Python 3.12+
* Node.js 20+

---

### Step 1: Backend Setup

1. **Navigate to backend and create a virtual environment**:
   ```bash
   cd backend
   python3 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

2. **Install requirements**:
   ```bash
   pip install -r requirements.txt
   ```
   > [!IMPORTANT]
   > On first launch, Ultralytics will automatically pull the standard `yolov8n.pt` model weights (~6.2MB).

3. **Run the FastAPI development server**:
   ```bash
   python main.py
   ```
   * **API Docs (Swagger UI)**: `http://localhost:8000/docs`
   * **Seeded Accounts**:
     * **Admin User**: Username `admin` | Password `admin` (Has polygon zone management, camera registration, and database purging capabilities)
     * **Guard User**: Username `guard` | Password `guard` (Has read-only dashboard access and alert resolve privileges)

---

### Step 2: Frontend Setup

1. **Navigate to the frontend directory and install dependencies**:
   ```bash
   cd ../frontend
   npm install
   ```

2. **Launch the Vite server**:
   ```bash
   npm run dev
   ```
   * **Dashboard console**: `http://localhost:5173`

---

## ⚙️ Advanced Configuration

### Telegram Integration Setup
To receive instant telemetric alerts directly on your mobile device:
1. Contact `@BotFather` on Telegram to create a new bot and copy the API token.
2. Get your numeric User ID or Chat ID from `@userinfobot`.
3. Open `backend/main.py` and modify the [Telegram Initializer](file:///home/tarun/smart-intrusion-detection/backend/main.py#L109-L112):
   ```python
   telegram = TelegramNotifier(
       bot_token="YOUR_TELEGRAM_BOT_TOKEN",
       chat_id="YOUR_TELEGRAM_CHAT_ID"
   )
   ```

### Camera Feeds Customization
Camera configurations are parsed from [cameras.json](file:///home/tarun/smart-intrusion-detection/backend/cameras.json). To configure RTSP IP cameras or physical USB webcams, modify the configuration:
```json
{
  "cameras": [
    {
      "id": "cam1",
      "name": "Server Room Entrance",
      "source": "rtsp://admin:password@192.168.1.100:554/stream1",
      "enabled": true
    },
    {
      "id": "webcam",
      "name": "Operator Desk Camera",
      "source": "0",
      "enabled": true
    }
  ]
}
```

---

## 📊 CV / AI Tuning Params

You can adjust parameters inside [detector.py](file:///home/tarun/smart-intrusion-detection/backend/detection/detector.py#L130-L136) to match your environment:

* `conf_threshold`: Adjust the float value (e.g. `0.45` to `0.70`). Higher values decrease false positives but may miss detections under poor lighting conditions.
* `model_name`: Switch from `yolov8n.pt` (Nano) to heavier model weights (`yolov8s.pt`, `yolov8m.pt`, or `yolov8l.pt`) if the CPU/GPU resources allow for increased spatial resolution.
* `max_age`: Increase this parameter in `ByteTrack` if objects are getting lost due to temporary occlusion.

---

## 👤 Author

**Tarun R**  
* B.E. CSE (Artificial Intelligence & Machine Learning)  
* SKCT Coimbatore | Batch 2024–2028  
* AI/ML Software Engineer Intern Project  
