import yaml
import time
import queue
import threading
import logging
import cv2
from typing import Dict, Any

from core.adapters.base import CameraSource
from core.adapters.rtsp import RTSPSource
from core.adapters.file_source import FileSource
from core.adapters.usb import USBSource
from core.pipeline.detector import Detector
from core.pipeline.tracker import Tracker
from core.pipeline.entry_exit import EntryExitLogic
from core.pipeline.posture import PostureLogic

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter factory — driven entirely by site_config.yaml `adapter:` field
#   file  → local .mp4 / .avi   (Stage 1: video testing)
#   rtsp  → RTSP IP camera      (Stage 2: recorded / live network feed)
#   usb   → webcam / USB cam    (Stage 3: live USB camera)
# ---------------------------------------------------------------------------
def build_adapter(cam_config: Dict[str, Any]) -> CameraSource:
    adapter_type = cam_config.get("adapter", "rtsp").lower()
    camera_id = cam_config["camera_id"]
    source = str(cam_config["source"])

    if adapter_type == "file":
        logger.info(f"[{camera_id}] Using FileSource  → {source}")
        return FileSource(camera_id, source)
    elif adapter_type == "usb":
        logger.info(f"[{camera_id}] Using USBSource   → device {source}")
        return USBSource(camera_id, source)
    else:  # rtsp (default)
        logger.info(f"[{camera_id}] Using RTSPSource  → {source}")
        return RTSPSource(camera_id, source)


class VisionRunner:
    def __init__(self, config_path: str, shared_queue: queue.Queue):
        self.config_path = config_path
        self.queue = shared_queue

        with open(self.config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.cameras_config = self._extract_cameras(self.config)
        self.threads = []
        self.running = False
        self.latest_frames = {}
        self.stopped_cameras = set()
        self.paused_cameras = set()

    def _extract_cameras(self, config: Dict[str, Any]) -> list:
        cameras = []
        for zone in config.get("zones", []):
            for cam in zone.get("cameras", []):
                cameras.append(cam)
        return cameras

    def _run_camera(self, cam_config: Dict[str, Any]):
        camera_id = cam_config["camera_id"]
        role = cam_config["role"]

        logger.info(f"[{camera_id}] Starting | role={role}")

        cam_source = build_adapter(cam_config)
        
        if not hasattr(self, 'adapters'):
            self.adapters = {}
        self.adapters[camera_id] = cam_source
        
        detector = Detector()
        tracker = Tracker(detector, frame_skip=cam_config.get("frame_skip", 1))

        entry_exit_logic = EntryExitLogic(cam_config) if role == "entry_exit" else None
        posture_logic = PostureLogic() if role == "posture" else None

        consecutive_none = 0
        MAX_NONE = 30  # stop after 30 consecutive None frames (file EOF or dead stream)

        while self.running and camera_id not in self.stopped_cameras:
            if camera_id in self.paused_cameras:
                time.sleep(0.1)
                continue
                
            frame = cam_source.read_frame()

            if frame is None:
                consecutive_none += 1
                if consecutive_none >= MAX_NONE:
                    logger.info(f"[{camera_id}] Stream ended. Looping to beginning.")
                    cam_source.set_position(0.0)
                    consecutive_none = 0
                time.sleep(0.05)
                continue
            consecutive_none = 0

            current_time = time.time()
            detections = tracker.process_frame(frame)

            if role == "entry_exit":
                # Pass ALL detections for this frame; get back {track_id: event} for
                # tracks that fired this frame (appeared or confirmed-absent).
                frame_events = entry_exit_logic.process_frame(detections, current_time)
                for track_id, event_type in frame_events.items():
                    # Find the bbox for this track (may be absent on exit — use last known)
                    match = next((d for d in detections if d.get("track_id") == track_id), None)
                    bbox = [round(v, 1) for v in match["bbox"]] if match else [0, 0, 0, 0]
                    event_dict = {
                        "camera_id": camera_id,
                        "timestamp": current_time,
                        "track_id": track_id,
                        "bbox": bbox,
                        "event": event_type,
                        "posture": None,
                    }
                    self.queue.put(event_dict)
                    logger.info(f"[{camera_id}] EVENT → {event_dict}")

            elif role == "posture":
                for d in detections:
                    track_id = d.get("track_id")
                    if track_id is None:
                        continue
                    posture_state = posture_logic.process(d.get("keypoints", []))
                    event_dict = {
                        "camera_id": camera_id,
                        "timestamp": current_time,
                        "track_id": track_id,
                        "bbox": [round(v, 1) for v in d["bbox"]],
                        "event": None,
                        "posture": posture_state,
                    }
                    self.queue.put(event_dict)
                    logger.info(f"[{camera_id}] EVENT → {event_dict}")

            # Draw basic bounding boxes for dashboard video feed
            annotated = frame.copy()
            for d in detections:
                bbox = d["bbox"]
                track_id = d.get("track_id", "")
                if bbox and len(bbox) == 4:
                    x1, y1, x2, y2 = map(int, bbox)
                    cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    cv2.putText(annotated, str(track_id), (x1, y1 - 10),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    
            # Resize for the web stream to reduce MJPEG latency and bandwidth on 4K/high-res videos
            annotated_resized = cv2.resize(annotated, (1280, 720))
            _, buffer = cv2.imencode('.jpg', annotated_resized, [cv2.IMWRITE_JPEG_QUALITY, 70])
            self.latest_frames[camera_id] = buffer.tobytes()

        cam_source.release()
        logger.info(f"[{camera_id}] Camera thread exited cleanly.")

    def start(self):
        self.running = True
        for cam_config in self.cameras_config:
            t = threading.Thread(
                target=self._run_camera,
                args=(cam_config,),
                name=f"cam-{cam_config['camera_id']}",
                daemon=True,
            )
            self.threads.append(t)
            t.start()
            logger.info(f"Thread started: {t.name}")

    def stop(self):
        logger.info("Stopping all camera threads...")
        self.running = False
        for t in self.threads:
            t.join(timeout=10)
        logger.info("All threads stopped.")
        
    def stop_camera(self, camera_id: str):
        logger.info(f"Stopping camera {camera_id}...")
        self.stopped_cameras.add(camera_id)
        if camera_id in self.latest_frames:
            del self.latest_frames[camera_id]
            
    def pause_camera(self, camera_id: str):
        self.paused_cameras.add(camera_id)

    def resume_camera(self, camera_id: str):
        self.paused_cameras.discard(camera_id)

    def seek_camera(self, camera_id: str, percent: float):
        # We need to find the cam_source adapter to call set_position
        # However, cam_source is local to _run_camera loop.
        # Let's save the adapter so we can access it globally.
        if hasattr(self, 'adapters') and camera_id in self.adapters:
            self.adapters[camera_id].set_position(percent)


# ---------------------------------------------------------------------------
# CLI entrypoint — for running standalone (stdout events)
# Usage: python -m core.main_vision config/site_config.yaml
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    config_file = sys.argv[1] if len(sys.argv) > 1 else "config/site_config.yaml"
    q = queue.Queue()
    runner = VisionRunner(config_file, q)

    try:
        runner.start()
        print(f"\n✅ Pipeline running. Reading config: {config_file}")
        print("   Press Ctrl+C to stop.\n")
        while True:
            try:
                ev = q.get(timeout=1.0)
                print(f"EVENT: {ev}")
            except queue.Empty:
                # Check if all threads are done (e.g. video file ended)
                if not any(t.is_alive() for t in runner.threads):
                    print("\n📹 All video sources exhausted. Done.")
                    break
    except KeyboardInterrupt:
        print("\n🛑 Interrupted by user.")
    finally:
        runner.stop()
