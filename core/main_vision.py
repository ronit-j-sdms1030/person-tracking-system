import yaml
import time
import queue
import threading
import logging
from typing import Dict, Any

from core.adapters.rtsp import RTSPSource
from core.pipeline.detector import Detector
from core.pipeline.tracker import Tracker
from core.pipeline.entry_exit import EntryExitLogic
from core.pipeline.posture import PostureLogic

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class VisionRunner:
    def __init__(self, config_path: str, shared_queue: queue.Queue):
        self.config_path = config_path
        self.queue = shared_queue
        
        with open(self.config_path, 'r') as f:
            self.config = yaml.safe_load(f)
            
        self.cameras_config = self._extract_cameras(self.config)
        self.threads = []
        self.running = False

    def _extract_cameras(self, config: Dict[str, Any]) -> list:
        cameras = []
        for zone in config.get('zones', []):
            for cam in zone.get('cameras', []):
                cameras.append(cam)
        return cameras

    def _run_camera(self, cam_config: Dict[str, Any]):
        camera_id = cam_config['camera_id']
        source = cam_config['source']
        role = cam_config['role']
        
        logger.info(f"Starting camera {camera_id} with role {role}")
        
        cam_source = RTSPSource(camera_id, source)
        detector = Detector()
        tracker = Tracker(detector, frame_skip=1)
        
        entry_exit_logic = None
        posture_logic = None
        
        if role == "entry_exit":
            entry_exit_logic = EntryExitLogic(cam_config)
        elif role == "posture":
            posture_logic = PostureLogic()
            
        while self.running:
            frame = cam_source.read_frame()
            if frame is None:
                time.sleep(0.1)
                continue
                
            current_time = time.time()
            detections = tracker.process_frame(frame)
            
            for d in detections:
                track_id = d.get('track_id')
                if track_id is None:
                    continue
                    
                event_type = None
                posture_state = None
                
                if role == "entry_exit":
                    event_type = entry_exit_logic.process(track_id, d['bbox'], current_time)
                    if event_type is None:
                        continue
                        
                elif role == "posture":
                    posture_state = posture_logic.process(d.get('keypoints', []))
                    
                event_dict = {
                    "camera_id": camera_id,
                    "timestamp": current_time,
                    "track_id": track_id,
                    "bbox": d['bbox'],
                    "event": event_type,
                    "posture": posture_state
                }
                self.queue.put(event_dict)
                logger.info(f"Emitted event: {event_dict}")
                
        cam_source.release()

    def start(self):
        self.running = True
        for cam_config in self.cameras_config:
            t = threading.Thread(target=self._run_camera, args=(cam_config,), daemon=True)
            self.threads.append(t)
            t.start()

    def stop(self):
        self.running = False
        for t in self.threads:
            t.join()

if __name__ == "__main__":
    import sys
    config_file = sys.argv[1] if len(sys.argv) > 1 else "../person-tracking-system-ref/config/site_config.yaml"
    q = queue.Queue()
    runner = VisionRunner(config_file, q)
    try:
        runner.start()
        while True:
            try:
                ev = q.get(timeout=1.0)
                # stdout for test verification
                print(f"EVENT: {ev}")
            except queue.Empty:
                pass
    except KeyboardInterrupt:
        runner.stop()
