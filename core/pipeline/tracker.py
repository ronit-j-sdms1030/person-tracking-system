import logging
from typing import List, Dict, Any
import numpy as np
from core.pipeline.detector import Detector

logger = logging.getLogger(__name__)

class Tracker:
    def __init__(self, detector: Detector, frame_skip: int = 1, patience: int = 2):
        self.detector = detector
        self.frame_skip = max(1, frame_skip)
        self.patience = patience
        self.frame_count = 0
        self.last_detections = []
        self.track_id_map = {}
        self.next_id = 1
        self.lost_tracks = {} # track_id -> {"det": dict, "age": int}

    def process_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        self.frame_count += 1
        
        if self.frame_count % self.frame_skip != 0 and self.last_detections:
            return self.last_detections

        # Run tracker
        detections = self.detector.track(frame)
        
        # Map raw ByteTrack IDs to sequential continuous IDs (1, 2, 3...)
        current_mapped_ids = set()
        for d in detections:
            raw_id = d.get('track_id')
            if raw_id is not None:
                if raw_id not in self.track_id_map:
                    self.track_id_map[raw_id] = self.next_id
                    self.next_id += 1
                d['track_id'] = self.track_id_map[raw_id]
                current_mapped_ids.add(d['track_id'])
                
                # If it was in lost_tracks, it's found again, remove it
                if d['track_id'] in self.lost_tracks:
                    del self.lost_tracks[d['track_id']]
        
        # Find tracks that were in last_detections but are missing now
        last_mapped_ids = {d.get('track_id'): d for d in self.last_detections if d.get('track_id') is not None}
        for tid, det in last_mapped_ids.items():
            if tid not in current_mapped_ids and tid not in self.lost_tracks:
                self.lost_tracks[tid] = {"det": det, "age": self.patience}
                
        # Age out lost tracks and append surviving ones to current detections
        to_remove = []
        for tid, data in self.lost_tracks.items():
            if tid not in current_mapped_ids:
                det = data["det"]
                b1 = det["bbox"]
                cx1 = (b1[0] + b1[2]) / 2.0
                cy1 = (b1[1] + b1[3]) / 2.0
                
                # Check for spatial overlap with current detections to avoid ghost duplicates
                is_duplicate = False
                for curr_det in detections:
                    b2 = curr_det["bbox"]
                    
                    # 1. IoU and IoM Check
                    ix1 = max(b1[0], b2[0]); iy1 = max(b1[1], b2[1])
                    ix2 = min(b1[2], b2[2]); iy2 = min(b1[3], b2[3])
                    iw = max(0, ix2 - ix1); ih = max(0, iy2 - iy1)
                    iou = 0
                    iom = 0
                    if iw > 0 and ih > 0:
                        inter = iw * ih
                        a1 = (b1[2]-b1[0]) * (b1[3]-b1[1])
                        a2 = (b2[2]-b2[0]) * (b2[3]-b2[1])
                        union = a1 + a2 - inter
                        iou = inter / union if union > 0 else 0
                        iom = inter / min(a1, a2) if min(a1, a2) > 0 else 0
                        
                    # 2. Center Distance Check
                    cx2 = (b2[0] + b2[2]) / 2.0
                    cy2 = (b2[1] + b2[3]) / 2.0
                    dist = ((cx1 - cx2) ** 2 + (cy1 - cy2) ** 2) ** 0.5
                    
                    if iou > 0.30 or iom > 0.60 or dist < 80.0:
                        is_duplicate = True
                        break
                        
                if is_duplicate:
                    to_remove.append(tid)
                    continue

                data["age"] -= 1
                if data["age"] > 0:
                    detections.append(det)
                else:
                    to_remove.append(tid)
                    
        for tid in to_remove:
            del self.lost_tracks[tid]
                
        self.last_detections = detections
        return detections
