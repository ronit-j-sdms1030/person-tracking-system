import logging
from typing import List, Dict, Any
import numpy as np
import os
from ultralytics import YOLO, RTDETR
import sys
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

class Detector:
    def __init__(self, model_path: str = "rtdetr-l.pt", fallback_model_path: str = "yolo11m.pt", conf_thresh: float = 0.20):
        self.conf_thresh = conf_thresh
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.head_model = None
        self.body_model = None
        self.is_fallback = False

        # 1. Primary Head Detector (CrowdHuman / Head Model) for high-accuracy headcount
        if os.path.exists("crowdhuman_yolov8n_best.pt"):
            logger.info("Loading Head Detector model: crowdhuman_yolov8n_best.pt")
            self.head_model = YOLO("crowdhuman_yolov8n_best.pt")
        elif os.path.exists("head_yolov8n.pt"):
            logger.info("Loading Head Detector model: head_yolov8n.pt")
            self.head_model = YOLO("head_yolov8n.pt")

        # 2. Body / Posture Model (Custom RT-DETR)
        try:
            if os.path.exists("rtdetr-custom.pt"):
                logger.info("Loading Primary Posture Model: rtdetr-custom.pt")
                self.body_model = RTDETR("rtdetr-custom.pt")
            else:
                head_model_path = "yolov8m-head.pt"
                if not os.path.exists(head_model_path):
                    logger.info("Downloading YOLOv8m head detection model...")
                    import urllib.request
                    urllib.request.urlretrieve("https://huggingface.co/keremberke/yolov8m-nlf-head-detection/resolve/main/best.pt", head_model_path)
                
                self.body_model = YOLO(head_model_path)
                self.is_fallback = True
        except Exception as e:
            logger.error(f"Failed to load body model: {e}")
            raise e

        self.model = self.head_model if self.head_model else self.body_model

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=False)

    def track(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=True)

    def _detect_or_track(self, frame: np.ndarray, track: bool = True) -> List[Dict[str, Any]]:
        head_detections = []
        if self.head_model:
            if track:
                head_results = self.head_model.track(frame, conf=self.conf_thresh, imgsz=512, persist=True, verbose=False, tracker="bytetrack.yaml")
            else:
                head_results = self.head_model(frame, conf=self.conf_thresh, imgsz=512, verbose=False)
            head_detections = self._parse_results(head_results)

        if head_detections:
            if self.body_model:
                body_results = self.body_model(frame, classes=[0,1], conf=self.conf_thresh, imgsz=512, verbose=False)
                body_detections = self._parse_results(body_results)
                
                b_boxes = [d["bbox"] for d in body_detections]
                b_cls = [d.get("class_id", 0) for d in body_detections]
                
                for hd in head_detections:
                    hx1, hy1, hx2, hy2 = hd["bbox"]
                    hcx, hcy = (hx1 + hx2) / 2, (hy1 + hy2) / 2
                    
                    best_cls = 0
                    best_bbox = None
                    min_dist = float('inf')
                    for b, c in zip(b_boxes, b_cls):
                        bx1, by1, bx2, by2 = b
                        if bx1 - 15 <= hcx <= bx2 + 15:
                            # Top-aligned distance between head top and body box top
                            dist = np.sqrt(((bx1 + bx2) / 2 - hcx) ** 2 + (by1 - hy1) ** 2)
                            if dist < min_dist:
                                min_dist = dist
                                best_cls = c
                                best_bbox = b
                    hd["class_id"] = best_cls
                    hd["body_bbox"] = best_bbox
                    if best_bbox is not None:
                        hd["bbox"] = best_bbox
            return head_detections

        classes = [0] if self.is_fallback else None
        if track:
            results = self.body_model.track(frame, classes=classes, conf=self.conf_thresh, imgsz=640, persist=True, verbose=False, tracker="bytetrack.yaml")
        else:
            results = self.body_model(frame, classes=classes, conf=self.conf_thresh, imgsz=640, verbose=False)
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
                cls_id = int(boxes[i].cls[0]) if boxes[i].cls is not None else 0
                kpts = result.keypoints[i].data[0].cpu().numpy().tolist() if has_kpts else None
                
                track_id = None
                if boxes[i].id is not None:
                    track_id = int(boxes[i].id[0])

                detections.append({
                    "bbox": box,
                    "keypoints": kpts,
                    "conf": conf,
                    "class_id": cls_id,
                    "track_id": track_id
                })
        
        return detections
