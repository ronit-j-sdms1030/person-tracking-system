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

_MODEL_CACHE = {}

def _apply_nms(detections: List[Dict], iou_threshold: float = 0.10, center_dist_px: float = 60.0) -> List[Dict]:
    """
    Two-stage deduplication for RT-DETR:
    Stage 1 — IoU NMS: removes boxes overlapping by > iou_threshold (catches same-size duplicates)
    Stage 2 — Center NMS: removes boxes whose centers are within center_dist_px pixels (catches different-size duplicates on same head)
    Keeps the highest-confidence box in each group.
    """
    if len(detections) <= 1:
        return detections
    # Sort by confidence descending
    dets = sorted(detections, key=lambda d: d.get("conf", 0), reverse=True)
    kept = []
    for det in dets:
        b1 = det["bbox"]
        cx1 = (b1[0] + b1[2]) / 2.0
        cy1 = (b1[1] + b1[3]) / 2.0
        drop = False
        for k in kept:
            b2 = k["bbox"]
            # Stage 1: IoU check
            ix1 = max(b1[0], b2[0]); iy1 = max(b1[1], b2[1])
            ix2 = min(b1[2], b2[2]); iy2 = min(b1[3], b2[3])
            iw = max(0, ix2 - ix1); ih = max(0, iy2 - iy1)
            inter = iw * ih
            a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
            a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
            union = a1 + a2 - inter
            iou = inter / union if union > 0 else 0
            if iou > iou_threshold:
                drop = True
                break
            # Stage 2: Center-distance check
            cx2 = (b2[0] + b2[2]) / 2.0
            cy2 = (b2[1] + b2[3]) / 2.0
            dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
            if dist < center_dist_px:
                drop = True
                break
        if not drop:
            kept.append(det)
    return kept

class Detector:
    def __init__(self, model_path: str = "rtdetr-l.pt", fallback_model_path: str = "yolo11m.pt", conf_thresh: float = 0.50, selected_model: str = "rtdetr"):
        self.conf_thresh = conf_thresh
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.is_fallback = False
        self.selected_model = selected_model

        # 1. Select Primary Model based on user choice
        # ONLY load the model the user selected — nothing else
        if selected_model == "yolo" and os.path.exists("fine_tuned_yolo.pt"):
            if "fine_tuned_yolo" in _MODEL_CACHE:
                self.body_model = _MODEL_CACHE["fine_tuned_yolo"]
            else:
                logger.info("Loading User Fine-Tuned Model: fine_tuned_yolo.pt (YOLOv8)")
                self.body_model = YOLO("fine_tuned_yolo.pt")
                _MODEL_CACHE["fine_tuned_yolo"] = self.body_model
            logger.info("Fine-Tuned YOLOv8 selected — skipping all other models.")
        else:
            # RT-DETR head detection only
            if "body_model" in _MODEL_CACHE:
                self.body_model = _MODEL_CACHE["body_model"]
            else:
                if os.path.exists("yoloh.pt"):
                    logger.info("Loading Primary Model: yoloh.pt (RT-DETR YOLOH)")
                    self.body_model = RTDETR("yoloh.pt")
                elif os.path.exists("rtdetr-custom.pt"):
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
                _MODEL_CACHE["body_model"] = self.body_model
            logger.info("RT-DETR selected — skipping sitting specialist and fallback models.")

        # Both paths: no secondary models loaded
        self.sitting_model = None
        self.head_model = None

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
        # 1. Primary Head Detection Model
        primary_dets = []
        # Model-specific thresholds:
        # RT-DETR (general model) needs higher conf to avoid furniture/sofa false positives
        # Fine-tuned YOLO is purpose-trained so can run at lower conf safely
        if self.selected_model == "yolo":
            infer_conf = 0.40  # Increased for safety to reduce false positives
            infer_iou  = 0.40
            # CLAHE: boost local contrast so dark-toned heads under CCTV lighting become visible
            import cv2 as _cv2
            _clahe = _cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            lab = _cv2.cvtColor(frame, _cv2.COLOR_BGR2LAB)
            l, a, b_ch = _cv2.split(lab)
            l = _clahe.apply(l)
            infer_frame = _cv2.cvtColor(_cv2.merge([l, a, b_ch]), _cv2.COLOR_LAB2BGR)
        else:  # rtdetr
            infer_conf = 0.75  # Increased for safety to reduce false positives
            infer_iou  = 0.30  # Very aggressive NMS — eliminates double boxes
            infer_frame = frame


        if self.body_model:
            try:
                with torch.inference_mode():
                    if track:
                        results = self.body_model.track(infer_frame, conf=infer_conf, iou=infer_iou, imgsz=640, persist=True, verbose=False, tracker="config/bytetrack_custom.yaml")
                    else:
                        results = self.body_model(infer_frame, conf=infer_conf, iou=infer_iou, imgsz=640, verbose=False)
                primary_dets = self._parse_results(results)
                # RT-DETR uses transformer matching — apply explicit Python NMS to remove duplicates
                if self.selected_model != "yolo":
                    primary_dets = _apply_nms(primary_dets, iou_threshold=0.35)
            except Exception as e:
                logger.warning(f"Primary head detection error, falling back to YOLO: {e}")

        if primary_dets:
            for d in primary_dets:
                d["head_bbox"] = d["bbox"]

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
                
                w = box[2] - box[0]
                h = box[3] - box[1]
                if w <= 0 or h <= 0:
                    continue
                aspect_ratio = w / h
                
                # Head Aspect Ratio (0.35 to 1.9) & Size Limits (8px to 400px)
                if not (0.35 <= aspect_ratio <= 1.9):
                    continue
                if not (8 <= w <= 400 and 8 <= h <= 400):
                    continue

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
