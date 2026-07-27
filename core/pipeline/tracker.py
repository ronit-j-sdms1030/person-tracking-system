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
        self.seen_track_ids = set()

    def process_frame(self, frame: np.ndarray) -> List[Dict[str, Any]]:
        self.frame_count += 1
        
        if self.frame_count % self.frame_skip != 0 and self.last_detections:
            # Return cached detections but don't increment track IDs or anything, 
            # maybe adjust logic if needed. 
            return self.last_detections

        # Run tracker
        detections = self.detector.track(frame)
        self.last_detections = detections
        
        # Log ID churn
        current_ids = {d['track_id'] for d in detections if d.get('track_id') is not None}
        new_ids = current_ids - self.seen_track_ids
        if new_ids:
            logger.info(f"New track IDs appeared: {new_ids}")
            self.seen_track_ids.update(new_ids)
            
        return detections
