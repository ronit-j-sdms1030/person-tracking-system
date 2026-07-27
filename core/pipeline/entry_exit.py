import time
from typing import Dict, Any, Optional
import numpy as np

class EntryExitLogic:
    def __init__(self, config: Dict[str, Any]):
        self.line_p1 = np.array(config['line']['p1'])
        self.line_p2 = np.array(config['line']['p2'])
        self.direction_in = config['direction_in']
        self.cooldown_seconds = config.get('cooldown_seconds', 2.0)
        self.cooldown_px = config.get('cooldown_px', 40.0)
        
        self.track_history = {}

    def _get_foot_point(self, bbox: list) -> np.ndarray:
        x1, y1, x2, y2 = bbox
        return np.array([(x1 + x2) / 2.0, y2])

    def _get_side(self, point: np.ndarray) -> int:
        v1 = self.line_p2 - self.line_p1
        v2 = point - self.line_p1
        cross_product = v1[0] * v2[1] - v1[1] * v2[0]
        return 1 if cross_product > 0 else -1

    def _is_entering(self, start_point: np.ndarray, end_point: np.ndarray) -> bool:
        dy = end_point[1] - start_point[1]
        dx = end_point[0] - start_point[0]
        
        if self.direction_in == "down":
            return dy > 0
        elif self.direction_in == "up":
            return dy < 0
        elif self.direction_in == "right":
            return dx > 0
        elif self.direction_in == "left":
            return dx < 0
        return True

    def process(self, track_id: int, bbox: list, current_time: float) -> Optional[str]:
        if track_id is None:
            return None
            
        point = self._get_foot_point(bbox)
        side = self._get_side(point)
        
        if track_id not in self.track_history:
            self.track_history[track_id] = {
                'last_side': side,
                'last_event_time': 0.0,
                'last_event_pos': None,
                'last_point': point
            }
            return None
            
        history = self.track_history[track_id]
        last_side = history['last_side']
        last_point = history['last_point']
        history['last_point'] = point
        
        event = None
        if side != last_side:
            last_event_time = history['last_event_time']
            last_event_pos = history['last_event_pos']
            
            time_ok = (current_time - last_event_time) > self.cooldown_seconds
            dist_ok = True
            if last_event_pos is not None:
                dist = np.linalg.norm(point - last_event_pos)
                dist_ok = dist > self.cooldown_px
                
            if time_ok and dist_ok:
                is_in = self._is_entering(last_point, point)
                event = "entered" if is_in else "exited"
                
                history['last_event_time'] = current_time
                history['last_event_pos'] = point
                
        history['last_side'] = side
        return event
