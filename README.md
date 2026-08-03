# Person Tracking System (Stark Vision)

A robust, real-time multicamera computer vision pipeline designed for tracking people, analyzing postures, and monitoring zone capacities using state-of-the-art AI models (YOLO and RT-DETR). 

## 🚀 Features

* **Multi-Camera Support:** Seamlessly connect RTSP streams, local MP4 files, or USB webcams. Each camera runs on its own isolated background thread for zero-lag performance.
* **Dual-Model Architecture:** 
  * **YOLO (Full Body):** Fine-tuned for full-body tracking.
  * **RT-DETR (Head Tracking):** Optimized for dense crowds and head detection, ignoring false positives like knees/shoes.
* **Smart Deduplication (IoM):** Custom Intersection over Minimum Area (IoM) algorithm seamlessly merges overlapping boxes (e.g., when the AI detects both a head and a full body for the same person) to ensure hyper-accurate counting.
* **Zombie Thread Protection:** Bulletproof thread lifecycle management ensures camera processors gracefully exit without memory leaks or Segmentation Faults during system resets.
* **Atomic Configuration:** Camera configurations (`site_config.yaml`) are saved atomically, completely preventing file corruption during sudden power losses or crashes.
* **Live Dashboard:** A beautiful, responsive web interface built on FastAPI and WebSockets providing live MJPEG video feeds, capacity alerts, and real-time event logs.
* **Posture & Movement Analytics:** Capable of differentiating between sitting and standing postures, and utilizing vector-based tracking for entry/exit gates.

## 🏗️ Architecture Components

1. **Core Vision Pipeline (`/core`)**
   * **`main_vision.py`**: The orchestration engine. Handles thread spawning, video ingestion, and routing frames through the AI.
   * **`detector.py`**: Runs inference and applies physical heuristics (aspect ratios, sizing, IoM suppression).
   * **`tracker.py`**: Maintains memory of tracked individuals across frames to handle occlusions and sudden model dropouts (configured with a 3.5s patience).
2. **State Management (`/state`)**
   * **`zone_state.py`**: Manages the logical capacity of the room (Total vs Present).
   * **`event_queue.py`**: The central nervous system bridging the AI threads with the web server.
3. **API Backend (`/api`)**
   * Powered by **FastAPI**. Exposes endpoints for managing cameras and streams real-time data to the UI over WebSockets.
4. **Frontend Dashboard (`/dashboard`)**
   * HTML/JS interface for managing the system, adding cameras, and viewing analytics.

## 🛠️ Setup & Installation

### Prerequisites
* Python 3.10+
* Git

### Installation
1. Clone the repository:
   ```bash
   git clone https://github.com/ronit-j-sdms1030/person-tracking-system.git
   cd person-tracking-system
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
   *(Ensure you install the correct PyTorch version for your CUDA/GPU setup if running hardware acceleration).*

## 🏃‍♂️ Running the System

To start the backend server and vision pipeline:

```bash
./start.sh
```
*(Or manually run `python -m uvicorn api.main:app --host 0.0.0.0 --port 8000`)*

Once started, open your web browser and navigate to:
**http://localhost:8000**

## ⚙️ Configuration
The system automatically generates and atomically manages a `config/site_config.yaml` file. You do not need to edit this file manually. Use the **Camera Setup Wizard** on the web dashboard to add streams, define zones, and assign AI models.

## 🛡️ License
Proprietary. Do not distribute without permission.