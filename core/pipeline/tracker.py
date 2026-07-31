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
                data["age"] -= 1
                if data["age"] > 0:
                    detections.append(data["det"])
                else:
                    to_remove.append(tid)
                    
        for tid in to_remove:
            del self.lost_tracks[tid]
                
        self.last_detections = detections
        return detections
