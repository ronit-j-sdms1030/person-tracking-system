import logging
from typing import List, Dict, Any
import numpy as np
import os
from ultralytics import YOLO, RTDETR

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, model_path: str = "rtdetr-l.pt", fallback_model_path: str = "yolo11m.pt", conf_thresh: float = 0.20):
        self.conf_thresh = conf_thresh
        self.model = None
        self.is_fallback = False

        # Try Primary Model (Custom RT-DETR fine-tuned for head/posture)
        try:
            logger.info(f"Loading Primary Model (RT-DETR): {model_path}")
            if os.path.exists("rtdetr-custom.pt"):
                self.model = RTDETR("rtdetr-custom.pt")
                logger.info("Custom RT-DETR loaded successfully.")
            else:
                # Use YOLOv8 head detection model as the placeholder/fallback
                import urllib.request
                head_model_path = "yolov8n-head.pt"
                if not os.path.exists(head_model_path):
                    logger.info("Downloading YOLOv8 head detection model...")
                    urllib.request.urlretrieve("https://huggingface.co/keremberke/yolov8n-nlf-head-detection/resolve/main/best.pt", head_model_path)
                
                self.model = YOLO(head_model_path)
                self.is_fallback = True
                logger.info(f"Fallback Head Model ({head_model_path}) loaded successfully because custom model is not ready.")
        except Exception as e:
            logger.error(f"Failed to load any model: {e}")
            raise e

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
