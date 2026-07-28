import os
import sys
import cv2
import time
import json
import queue
import threading
import numpy as np
from flask import Flask, render_template, request, Response, jsonify

# Make core/ importable from test_app/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.pipeline.detector import Detector
from core.pipeline.tracker import Tracker
from core.pipeline.entry_exit import EntryExitLogic
from core.pipeline.posture import PostureLogic

# ── COCO skeleton for keypoint visualization ──────────────────────────────
SKELETON = [
    (0,1),(0,2),(1,3),(2,4),          # face
    (5,6),(5,7),(7,9),(6,8),(8,10),   # arms
    (5,11),(6,12),(11,12),            # torso
    (11,13),(13,15),(12,14),(14,16),  # legs
]
KPT_COLOR  = (0, 255, 180)
BONE_COLOR = (0, 180, 255)

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "sample_videos")
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)

# ── Shared session state ──────────────────────────────────────────────────
_lock         = threading.Lock()
_frame_q      = queue.Queue(maxsize=4)
_event_q      = queue.Queue()
_stop_event   = threading.Event()
_stats        = {"entered": 0, "exited": 0, "posture": {"sitting": 0, "standing": 0, "unknown": 0}}
_event_log    = []          # list of dicts for the log panel
_last_posture = {}          # dict tracking last known posture per track_id to prevent spam
_proc_thread  = None


# ─────────────────────────────────────────────────────────────────────────────
# Frame annotation helpers
# ─────────────────────────────────────────────────────────────────────────────
def _draw_box(frame, bbox, track_id, label, color):
    x1, y1, x2, y2 = [int(v) for v in bbox]
    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
    txt = f"ID:{track_id} {label}"
    (tw, th), _ = cv2.getTextSize(txt, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 1)
    cv2.rectangle(frame, (x1, y1 - th - 6), (x1 + tw + 4, y1), color, -1)
    cv2.putText(frame, txt, (x1 + 2, y1 - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0,0,0), 1, cv2.LINE_AA)


def _draw_skeleton(frame, keypoints):
    kpts = np.array(keypoints)
    for i, (x, y, c) in enumerate(kpts):
        if c > 0.4:
            cv2.circle(frame, (int(x), int(y)), 3, KPT_COLOR, -1)
    for a, b in SKELETON:
        if kpts[a][2] > 0.4 and kpts[b][2] > 0.4:
            p1 = (int(kpts[a][0]), int(kpts[a][1]))
            p2 = (int(kpts[b][0]), int(kpts[b][1]))
            cv2.line(frame, p1, p2, BONE_COLOR, 1)


def _encode_jpeg(frame):
    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
    return buf.tobytes()


# ─────────────────────────────────────────────────────────────────────────────
# Background processing thread
# ─────────────────────────────────────────────────────────────────────────────
def _process_video(video_path: str, role: str, camera_id: str, cooldown: float):
    global _stats, _event_log

    with _lock:
        _stats = {"entered": 0, "exited": 0,
                  "posture": {"sitting": 0, "standing": 0, "unknown": 0}}
        _event_log.clear()
        _last_posture.clear()

    detector = Detector()
    tracker  = Tracker(detector, frame_skip=1)
    config   = {"camera_id": camera_id, "cooldown_seconds": cooldown}
    ee_logic = EntryExitLogic(config) if role in ("entry_exit", "both") else None
    p_logic  = PostureLogic()         if role in ("posture", "both") else None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        _event_q.put({"type": "error", "message": f"Cannot open: {video_path}"})
        return

    fps     = cap.get(cv2.CAP_PROP_FPS) or 25
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_n = 0

    while not _stop_event.is_set():
        ret, frame = cap.read()
        if not ret:
            break

        frame_n += 1
        current_time = time.time()
        detections   = tracker.process_frame(frame)
        annotated    = frame.copy()

        # ── Entry / Exit ────────────────────────────────────────────────
        if ee_logic:
            frame_events = ee_logic.process_frame(detections, current_time)
            for d in detections:
                tid = d.get("track_id")
                if tid is None:
                    continue
                ev      = frame_events.get(tid)
                color   = (0, 255, 100) if ev == "entered" else \
                          (0, 80, 255)  if ev == "exited"  else (200, 200, 200)
                
                # If we also have posture, don't overwrite the color/label here if not an event
                if p_logic and not ev:
                    pass
                else:
                    label   = ev.upper() if ev else ""
                    _draw_box(annotated, d["bbox"], tid, label, color)

            for tid, ev in frame_events.items():
                with _lock:
                    if ev == "entered": _stats["entered"] += 1
                    else:               _stats["exited"]  += 1
                entry = {
                    "time":      time.strftime("%H:%M:%S"),
                    "track_id":  tid,
                    "event":     ev,
                    "posture":   None,
                    "camera_id": camera_id,
                }
                _event_log.append(entry)
                _event_q.put({"type": "event", "data": entry, "stats": dict(_stats)})

        # ── Posture ─────────────────────────────────────────────────────
        if p_logic:
            frame_posture_counts = {"sitting": 0, "standing": 0, "unknown": 0}
            for d in detections:
                tid = d.get("track_id")
                if tid is None:
                    continue
                posture = p_logic.process(d.get("keypoints", []))
                color   = (100, 255, 100) if posture == "standing" else \
                          (255, 180, 50)  if posture == "sitting"  else (180,180,180)
                
                # Draw skeleton and posture box (won't overwrite entry/exit flash if we are careful, 
                # but simplest is just draw posture box)
                _draw_box(annotated, d["bbox"], tid, posture, color)
                if d.get("keypoints"):
                    _draw_skeleton(annotated, d["keypoints"])
                
                frame_posture_counts[posture] += 1
                
                # Only log/emit an event if the posture CHANGED for this track_id
                if posture != _last_posture.get(tid):
                    _last_posture[tid] = posture
                    entry = {
                        "time":      time.strftime("%H:%M:%S"),
                        "track_id":  tid,
                        "event":     None,
                        "posture":   posture,
                        "camera_id": camera_id,
                    }
                    _event_log.append(entry)
                    _event_q.put({"type": "event", "data": entry, "stats": dict(_stats)})
                    
            with _lock:
                _stats["posture"] = frame_posture_counts
                
            # If we want the UI to update the numbers even when no event fires, 
            # we can push a "stats_only" update to the SSE stream. But for now,
            # it updates alongside any events. Actually, let's push a stats update every frame
            # if we want the numbers to be perfectly live, or just let it update on the next event.
            # To be safe and keep it live, push a stats update every frame without an event data:
            _event_q.put({"type": "event", "data": None, "stats": dict(_stats)})

        # Progress overlay
        pct = int(frame_n / total * 100) if total else 0
        cv2.putText(annotated, f"Frame {frame_n}/{total} ({pct}%)",
                    (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

        # Push frame (drop if full to keep UI smooth)
        try:
            _frame_q.put_nowait(_encode_jpeg(annotated))
        except queue.Full:
            pass

        # Throttle to ~real-time
        time.sleep(1.0 / fps)

    cap.release()
    _event_q.put({"type": "done", "stats": dict(_stats)})


# ─────────────────────────────────────────────────────────────────────────────
# Flask routes
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload():
    global _proc_thread

    # Stop any running session
    _stop_event.set()
    if _proc_thread and _proc_thread.is_alive():
        _proc_thread.join(timeout=3)
    _stop_event.clear()

    # Drain queues
    for q in (_frame_q, _event_q):
        while not q.empty():
            try: q.get_nowait()
            except: pass

    f          = request.files.get("video")
    role       = request.form.get("role", "entry_exit")
    camera_id  = request.form.get("camera_id", "cam_test")
    cooldown   = float(request.form.get("cooldown", 2.0))

    if not f:
        return jsonify({"error": "No file provided"}), 400

    save_path = os.path.join(UPLOAD_DIR, f.filename)
    f.save(save_path)

    _proc_thread = threading.Thread(
        target=_process_video,
        args=(save_path, role, camera_id, cooldown),
        daemon=True,
    )
    _proc_thread.start()
    return jsonify({"status": "started", "file": f.filename, "role": role})


@app.route("/video_feed")
def video_feed():
    def generate():
        while True:
            if _stop_event.is_set():
                break
            try:
                frame_bytes = _frame_q.get(timeout=1.0)
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" +
                       frame_bytes + b"\r\n")
            except queue.Empty:
                continue
    return Response(generate(),
                    mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/event_stream")
def event_stream():
    def generate():
        while True:
            try:
                msg = _event_q.get(timeout=1.0)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg.get("type") == "done":
                    break
            except queue.Empty:
                yield "data: {\"type\": \"ping\"}\n\n"
    return Response(generate(), mimetype="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.route("/stats")
def stats():
    with _lock:
        return jsonify(_stats)


@app.route("/stop", methods=["POST"])
def stop():
    _stop_event.set()
    return jsonify({"status": "stopped"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False, threaded=True)
