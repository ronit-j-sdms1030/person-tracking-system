import logging
from typing import List, Dict, Any
import numpy as np
from core.pipeline.detector import Detector

logger = logging.getLogger(__name__)

class Tracker:
    def __init__(self, detector: Detector, frame_skip: int = 1):
        self.detector = detector
        self.frame_skip = max(1, frame_skip)
        self.frame_count = 0
        self.last_detections = []
        self.track_id_map = {}
        self.next_id = 1

    def process_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        self.frame_count += 1
        
        if self.frame_count % self.frame_skip != 0 and self.last_detections:
            # Return cached detections but don't increment track IDs or anything, 
            # maybe adjust logic if needed. 
            return self.last_detections

        # Run tracker
        detections = self.detector.track(frame)
        
        # Map raw ByteTrack IDs to sequential continuous IDs (1, 2, 3...)
        for d in detections:
            raw_id = d.get('track_id')
            if raw_id is not None:
                if raw_id not in self.track_id_map:
                    self.track_id_map[raw_id] = self.next_id
                    self.next_id += 1
                d['track_id'] = self.track_id_map[raw_id]
                
        self.last_detections = detections
            
        return detections
