import logging
from typing import List, Dict, Any
import numpy as np
from ultralytics import YOLO, RTDETR

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, model_path: str = "rtdetr-l.pt", fallback_model_path: str = "yolo11m.pt", conf_thresh: float = 0.25):
        self.conf_thresh = conf_thresh
        self.model = None
        self.is_fallback = False

        # Try Primary Model (RT-DETR / Apache 2.0)
        try:
            logger.info(f"Loading Primary Model (RT-DETR): {model_path}")
            if "rtdetr" in model_path.lower():
                self.model = RTDETR(model_path)
            else:
                self.model = YOLO(model_path)
            logger.info("Primary Model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load primary model {model_path}: {e}. Activating Fallback Model: {fallback_model_path}")
            try:
                self.model = YOLO(fallback_model_path)
                self.is_fallback = True
                logger.info(f"Fallback Model ({fallback_model_path}) loaded successfully.")
            except Exception as e2:
                logger.error(f"Failed to load fallback model {fallback_model_path}: {e2}")
                raise e2

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
