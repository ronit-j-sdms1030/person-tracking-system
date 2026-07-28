import logging
from typing import List, Dict, Any
import numpy as np
from ultralytics import YOLO

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, model_path: str = "yolov8n-head.pt", conf_thresh: float = 0.25):
        logger.info(f"Loading YOLO model from {model_path}")
        self.model = YOLO(model_path)
        self.conf_thresh = conf_thresh

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        results = self.model(frame, classes=[0], conf=self.conf_thresh, verbose=False)
        return self._parse_results(results)

    def track(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        results = self.model.track(frame, classes=[0], conf=self.conf_thresh, persist=True, verbose=False, tracker="bytetrack.yaml")
        return self._parse_results(results)

    def _parse_results(self, results) -> List[Dict[str, Any]]:
        detections = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue

            has_kpts = hasattr(result, 'keypoints') and result.keypoints is not None

            for i in range(len(boxes)):
                box = boxes[i].xyxy[0].cpu().numpy().tolist()
                conf = float(boxes[i].conf[0])
                kpts = result.keypoints[i].data[0].cpu().numpy().tolist() if has_kpts else None
                
                track_id = None
                if boxes[i].id is not None:
                    track_id = int(boxes[i].id[0])

                detections.append({
                    "bbox": box,
                    "keypoints": kpts,
                    "conf": conf,
                    "track_id": track_id
                })
        return detections
