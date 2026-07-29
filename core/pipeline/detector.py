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

        # 1. Primary Model: Custom RT-DETR (rtdetr-custom.pt) for primary headcount & posture tracking
        if os.path.exists("rtdetr-custom.pt"):
            logger.info("Loading Primary Headcount & Posture Model: rtdetr-custom.pt (RT-DETR)")
            self.body_model = RTDETR("rtdetr-custom.pt")
        else:
            head_model_path = "yolov8m-head.pt"
            if not os.path.exists(head_model_path):
                logger.info("Downloading YOLOv8m head detection model...")
                import urllib.request
                urllib.request.urlretrieve("https://huggingface.co/keremberke/yolov8m-nlf-head-detection/resolve/main/best.pt", head_model_path)
            self.body_model = YOLO(head_model_path)
            self.is_fallback = True

        # 2. Fallback / Auxiliary Head Detector (CrowdHuman YOLO)
        if os.path.exists("crowdhuman_yolov8n_best.pt"):
            logger.info("Loading Fallback Head Detector model: crowdhuman_yolov8n_best.pt (YOLO)")
            self.head_model = YOLO("crowdhuman_yolov8n_best.pt")
        elif os.path.exists("head_yolov8n.pt"):
            logger.info("Loading Fallback Head Detector model: head_yolov8n.pt (YOLO)")
            self.head_model = YOLO("head_yolov8n.pt")

        self.model = self.body_model if self.body_model else self.head_model

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=False)

    def track(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=True)

    def _detect_or_track(self, frame: np.ndarray, track: bool = True) -> List[Dict[str, Any]]:
        # 1. Primary RT-DETR Detection & Tracking
        classes = [0, 1] if not self.is_fallback else [0]
        if track:
            rtdetr_results = self.body_model.track(frame, classes=classes, conf=self.conf_thresh, imgsz=640, persist=True, verbose=False, tracker="bytetrack.yaml")
        else:
            rtdetr_results = self.body_model(frame, classes=classes, conf=self.conf_thresh, imgsz=640, verbose=False)
        rtdetr_detections = self._parse_results(rtdetr_results)

        # If primary RT-DETR returned detections, use RT-DETR for headcount and associate CrowdHuman head boxes if available
        if rtdetr_detections:
            if self.head_model:
                head_results = self.head_model(frame, conf=self.conf_thresh, imgsz=512, verbose=False)
                head_detections = self._parse_results(head_results)
                
                h_boxes = [hd["bbox"] for hd in head_detections]
                for rd in rtdetr_detections:
                    bx1, by1, bx2, by2 = rd["bbox"]
                    bcx = (bx1 + bx2) / 2
                    
                    best_h = None
                    min_dist = float('inf')
                    for h in h_boxes:
                        hx1, hy1, hx2, hy2 = h
                        hcx = (hx1 + hx2) / 2
                        if bx1 - 15 <= hcx <= bx2 + 15:
                            dist = np.sqrt((bcx - hcx) ** 2 + (by1 - hy1) ** 2)
                            if dist < min_dist:
                                min_dist = dist
                                best_h = h
                    if best_h is not None:
                        rd["head_bbox"] = best_h
            return rtdetr_detections

        # 2. Fallback to YOLO CrowdHuman Head Detector if RT-DETR is empty
        if self.head_model:
            logger.debug("Primary RT-DETR empty. Using Fallback YOLO Head Detector.")
            if track:
                head_results = self.head_model.track(frame, conf=self.conf_thresh, imgsz=512, persist=True, verbose=False, tracker="bytetrack.yaml")
            else:
                head_results = self.head_model(frame, conf=self.conf_thresh, imgsz=512, verbose=False)
            return self._parse_results(head_results)

        return []

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
