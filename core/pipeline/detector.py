import logging
from typing import List, Dict, Any
import numpy as np
import os
from ultralytics import YOLO, RTDETR
import sys
import torch
import torch.nn.functional as F

logger = logging.getLogger(__name__)

class DetResults:
    def __init__(self, xyxy, conf, cls):
        self.xyxy = torch.as_tensor(xyxy, dtype=torch.float32)
        self.conf = torch.as_tensor(conf, dtype=torch.float32)
        self.cls = torch.as_tensor(cls, dtype=torch.float32)
        
        if self.xyxy.ndim == 1 and len(self.xyxy) > 0:
            self.xyxy = self.xyxy.unsqueeze(0)
            self.conf = self.conf.unsqueeze(0)
            self.cls = self.cls.unsqueeze(0)
            
        x1 = self.xyxy[:, 0] if len(self.xyxy) > 0 else torch.empty(0)
        y1 = self.xyxy[:, 1] if len(self.xyxy) > 0 else torch.empty(0)
        x2 = self.xyxy[:, 2] if len(self.xyxy) > 0 else torch.empty(0)
        y2 = self.xyxy[:, 3] if len(self.xyxy) > 0 else torch.empty(0)
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        w = x2 - x1
        h = y2 - y1
        self.xywh = torch.stack([cx, cy, w, h], dim=-1) if len(self.xyxy) > 0 else torch.empty((0, 4))
        
    def __len__(self):
        return len(self.xyxy)
        
    def __getitem__(self, idx):
        return DetResults(self.xyxy[idx], self.conf[idx], self.cls[idx])

class Detector:
    def __init__(self, model_path: str = "rtdetr-l.pt", fallback_model_path: str = "yolo11m.pt", conf_thresh: float = 0.50):
        self.conf_thresh = conf_thresh
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.head_model = None
        self.body_model = None
        self.is_fallback = False

        # 1. Primary Model: Custom RT-DETR (rtdetr-custom.pt) for primary headcount
        if os.path.exists("rtdetr-custom.pt"):
            logger.info("Loading Primary Headcount Model: rtdetr-custom.pt (RT-DETR)")
            self.body_model = RTDETR("rtdetr-custom.pt")
        else:
            head_model_path = "yolov8m-head.pt"
            if not os.path.exists(head_model_path):
                logger.info("Downloading YOLOv8m head detection model...")
                import urllib.request
                urllib.request.urlretrieve("https://huggingface.co/keremberke/yolov8m-nlf-head-detection/resolve/main/best.pt", head_model_path)
            self.body_model = YOLO(head_model_path)
            self.is_fallback = True

        # 1b. Sitting Specialist Model: best (1).pt (rtdetr_sitting_best.pt)
        self.sitting_model = None
        if os.path.exists("rtdetr_sitting_best.pt"):
            logger.info("Loading Sitting Specialist RT-DETR Model: rtdetr_sitting_best.pt (best (1).pt)")
            self.sitting_model = RTDETR("rtdetr_sitting_best.pt")

        # 2. Fine-Tuned Head Detector Model: headmodel.pt (User-Provided Fine-Tuned Head Model)
        if os.path.exists("headmodel.pt"):
            logger.info("Loading User Fine-Tuned Head Detector Model: headmodel.pt (YOLO)")
            self.head_model = YOLO("headmodel.pt")
            self.use_yolox = False
        elif os.path.exists("crowdhuman_yolov8n_best.pt"):
            logger.info("Loading Fine-Tuned Head Detector Model: crowdhuman_yolov8n_best.pt (YOLO)")
            self.head_model = YOLO("crowdhuman_yolov8n_best.pt")
            self.use_yolox = False
        elif os.path.exists("head_yolov8n.pt"):
            logger.info("Loading Fine-Tuned Head Detector Model: head_yolov8n.pt (YOLO)")
            self.head_model = YOLO("head_yolov8n.pt")
            self.use_yolox = False
        else:
            self.use_yolox = False

        self.model = self.body_model if self.body_model else getattr(self, "head_model", None)

    def detect(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=False)

    def track(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        return self._detect_or_track(frame, track=True)

    def _detect_or_track(self, frame: np.ndarray, track: bool = True) -> List[Dict[str, Any]]:
        # 1. User-Requested Primary Head Detector (YOLOX Nano Head Model)
        head_detections = []
        if getattr(self, "use_yolox", False) and getattr(self, "yolox_model", None) is not None:
            fh, fw, _ = frame.shape
            img, _ = self.val_transform(frame, None, (416, 416))
            img_t = torch.from_numpy(img).unsqueeze(0).float().to(self.device)
            ratio = min(416 / fh, 416 / fw)
            
            with torch.no_grad():
                outputs = self.yolox_model(img_t)
                from yolox.utils import postprocess
                outputs = postprocess(outputs, self.yolox_exp.num_classes, self.conf_thresh, 0.45)
                
            if outputs[0] is not None:
                boxes = outputs[0][:, :4].cpu().numpy() / ratio
                scores = outputs[0][:, 4].cpu().numpy() * outputs[0][:, 5].cpu().numpy()
                
                if track and hasattr(self, "yolox_tracker"):
                    det_res = DetResults(boxes, scores, np.zeros(len(boxes)))
                    tracks = self.yolox_tracker.update(det_res, img=frame)
                    if tracks is not None and len(tracks) > 0:
                        for t in tracks:
                            head_detections.append({
                                "bbox": [float(t[0]), float(t[1]), float(t[2]), float(t[3])],
                                "confidence": float(t[5]),
                                "class_id": 0,
                                "track_id": int(t[4])
                            })
                    else:
                        for i, (b, s) in enumerate(zip(boxes, scores)):
                            head_detections.append({
                                "bbox": [float(b[0]), float(b[1]), float(b[2]), float(b[3])],
                                "confidence": float(s),
                                "class_id": 0,
                                "track_id": i + 1
                            })
                else:
                    for i, (b, s) in enumerate(zip(boxes, scores)):
                        head_detections.append({
                            "bbox": [float(b[0]), float(b[1]), float(b[2]), float(b[3])],
                            "confidence": float(s),
                            "class_id": 0,
                            "track_id": i + 1
                        })
        # 1. Primary Head Detection Model: RT-DETR Head Model (retr detr head / rtdetr-custom.pt)
        primary_dets = []
        if self.body_model:
            try:
                with torch.inference_mode():
                    if track:
                        results = self.body_model.track(frame, conf=0.24, imgsz=640, persist=True, verbose=False, tracker="bytetrack.yaml")
                    else:
                        results = self.body_model(frame, conf=0.24, imgsz=640, verbose=False)
                primary_dets = self._parse_results(results)
            except Exception as e:
                logger.warning(f"RT-DETR primary head detection error, falling back to YOLO: {e}")

        # 2. Fallback Head Detection Model: Fine-Tuned YOLO Head Model (headmodel.pt)
        if not primary_dets and self.head_model:
            with torch.inference_mode():
                if track:
                    head_results = self.head_model.track(frame, conf=0.24, imgsz=512, persist=True, verbose=False, tracker="bytetrack.yaml")
                else:
                    head_results = self.head_model(frame, conf=0.24, imgsz=512, verbose=False)
            primary_dets = self._parse_results(head_results)

        if primary_dets:
            for d in primary_dets:
                d["head_bbox"] = d["bbox"]

            # 3. Sitting Specialist RT-DETR Model (best (1).pt): Use exclusively for Sitting posture detection
            if getattr(self, "sitting_model", None) is not None:
                try:
                    with torch.inference_mode():
                        sit_res = self.sitting_model(frame, conf=0.24, verbose=False)
                    sit_dets = self._parse_results(sit_res)
                    sit_boxes = [s["bbox"] for s in sit_dets if s.get("class_id") == 0]

                    for d in primary_dets:
                        hb = d["bbox"]
                        cx, cy = (hb[0] + hb[2]) / 2.0, (hb[1] + hb[3]) / 2.0
                        # Mark class_id = 0 (Sitting) if inside a sitting box from best(1).pt
                        if any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in sit_boxes):
                            d["class_id"] = 0 # Sitting
                        else:
                            d["class_id"] = 1 # Standing
                except Exception as e:
                    logger.debug(f"Sitting specialist RT-DETR error: {e}")

            return primary_dets

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
