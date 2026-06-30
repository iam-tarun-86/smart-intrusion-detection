# 🔐 Smart Intrusion Detection System

Real-time AI-powered intrusion detection using YOLOv8, FastAPI, and React.

![Dashboard Screenshot](docs/screenshot.png)

## 🎯 Features

- **Real-time person detection** with YOLOv8
- **Restricted zone monitoring** with configurable polygons
- **Instant WebSocket alerts** when intrusion detected
- **Live MJPEG video stream** in browser dashboard
- **Event logging** with SQLite/PostgreSQL
- **Resolve/acknowledge** alerts from dashboard

## 🏗️ System Architecture

```
[Camera/Video Feed]
        |
        v
[OpenCV — Frame Capture]
        |
        v
[YOLOv8 — Person Detection]
        |
        v
[Zone Logic — Intrusion Check]
        |
   _____|_____
  |           |
  v           v
[SQLite/DB]  [WebSocket Push]
(Event Logs)       |
                   v
           [React Dashboard]
           - Live Feed
           - Alert Panel
           - Logs Table
```

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| Object Detection | YOLOv8 (Ultralytics) |
| Video Processing | OpenCV |
| Backend API | FastAPI |
| Real-time Communication | WebSockets |
| Frontend Dashboard | React + Vite |
| Database | SQLite (dev) / PostgreSQL (prod) |
| Styling | CSS3 |

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Node.js 20+
- (Optional) PostgreSQL for production

### 1. Clone & Setup Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run Backend

```bash
python main.py
# API runs at http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

### 3. Setup Frontend (new terminal)

```bash
cd frontend
npm install
```

### 4. Run Frontend

```bash
npm run dev
# Dashboard at http://localhost:5173
```

## 📊 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | API status |
| GET | `/stream` | MJPEG video stream |
| GET | `/alerts` | List intrusion events |
| POST | `/alerts/{id}/resolve` | Mark alert resolved |
| GET | `/stats` | System statistics |
| GET | `/zones` | Zone configurations |
| WS | `/ws` | Real-time alert stream |

## 📁 Project Structure

```
smart-intrusion-detection/
├── backend/
│   ├── detection/
│   │   ├── detector.py      # YOLOv8 inference
│   │   └── zones.py         # Zone definition & intrusion logic
│   ├── db/
│   │   ├── models.py        # Database models
│   │   └── database.py      # DB connection
│   ├── main.py              # FastAPI entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── VideoFeed.jsx
│   │   │   ├── AlertPanel.jsx
│   │   │   └── LogsTable.jsx
│   │   ├── App.jsx
│   │   └── App.css
│   └── package.json
├── docs/
│   └── screenshot.png
└── README.md
```

## ⚙️ Configuration

### Adding Restricted Zones

Edit `backend/main.py` and modify the zone definitions in `init_system()`:

```python
zone_manager.add_zone(Zone(
    name="Server Room",
    points=[(400, 150), (700, 150), (700, 350), (400, 350)],
    color=(0, 0, 255),
    severity="high"
))
```

### Tuning Detection

Adjust parameters in `backend/detection/detector.py`:

| Parameter | Default | Description |
|-----------|---------|-------------|
| `conf_threshold` | 0.5 | Minimum confidence for person detection |
| `model_name` | yolov8n.pt | YOLOv8 model variant (n/s/m/l/x) |

## 🎥 Demo

[Add your demo video or GIF here]

## 📝 Resume Highlights

- Built a **real-time intrusion detection system** using **YOLOv8** and **OpenCV**, achieving person detection with configurable restricted zones
- Developed **FastAPI** backend with **WebSocket** support for sub-second alert delivery to a live **React** monitoring dashboard
- Integrated **SQLite** event logging with snapshot storage for audit trails and compliance reporting
- Designed responsive **dark-themed UI** with real-time video feed, alert panel, and event logs table

## 📚 Learning Resources

- [YOLOv8 Docs — Ultralytics](https://docs.ultralytics.com)
- [OpenCV Python Tutorials](https://docs.opencv.org/4.x/d6/d00/tutorial_py_root.html)
- [FastAPI Official Docs](https://fastapi.tiangolo.com)
- [FastAPI WebSockets Guide](https://fastapi.tiangolo.com/advanced/websockets/)

## 👤 Author

**Tarun R**  
B.E. CSE (AI & ML)  
SKCT Coimbatore  
Batch 2024–2028

---

*Built as an AI/ML Intern project. Feel free to fork and extend!*
