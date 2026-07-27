# person-tracking-system

## Person A — Vision & Tracking Core

This repository contains the **vision and tracking** half of the CCTV people-counting prototype, built by **Person A** against the shared contract defined in `contract.md`.

---

## Folder Structure

```
person-tracking-system/
├── config/
│   └── site_config.yaml        # Site + camera config (shared with Person B)
├── contract.md                 # Shared event schema & queue interface
├── requirements.txt            # Python dependencies
├── validate.py                 # Phase 5: Validation protocol script
├── data/
│   └── sample_videos/          # Place test .mp4 files here (git-ignored)
├── logs/                       # Validation CSV/JSON output (git-ignored)
└── core/
    ├── main_vision.py          # Entrypoint — wires adapters + pipeline → queue
    ├── adapters/
    │   ├── base.py             # Abstract CameraSource class
    │   └── rtsp.py             # RTSPSource (also handles local video files)
    └── pipeline/
        ├── detector.py         # YOLOv8n-pose wrapper (class 0 / person only)
        ├── tracker.py          # ByteTrack integration + frame-skip logic
        ├── entry_exit.py       # Line-crossing + cooldown (entry/exit events)
        └── posture.py          # Keypoint-angle posture classification
```

---

## Setup

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

> First run will auto-download `yolov8n-pose.pt` from Ultralytics.

---

## Running

### Single camera (stdout events):

```bash
python -m core.main_vision config/site_config.yaml
```

### Both cameras concurrently:

`main_vision.py` reads all cameras from `site_config.yaml` and spawns a thread per camera automatically.

### Integration with Person B:

Pass a shared `queue.Queue()` to `VisionRunner`:

```python
import queue
from core.main_vision import VisionRunner

shared_q = queue.Queue()   # Same instance Person B's consumer uses
runner = VisionRunner("config/site_config.yaml", shared_q)
runner.start()
```

---

## Validation (Phase 5)

Place test videos in `data/sample_videos/` then run:

```bash
# Entry/exit accuracy (20 walkthroughs)
python validate.py --config config/site_config.yaml --mode entry_exit

# Posture accuracy (30 spot-checks)
python validate.py --config config/site_config.yaml --mode posture
```

Results are saved to `logs/` as CSV + JSON summary with accuracy %.

---

## Event Schema (from contract.md)

```json
{
  "camera_id": "cam_door_1",
  "timestamp": 1234567890.12,
  "track_id": 17,
  "bbox": [x1, y1, x2, y2],
  "event": "entered" | "exited" | null,
  "posture": "sitting" | "standing" | "unknown" | null
}
```

- `event` is non-null only for `role: entry_exit` cameras, fires once per crossing after cooldown.
- `posture` is non-null only for `role: posture` cameras, emitted every frame.
- `event` and `posture` are mutually exclusive.