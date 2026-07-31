import numpy as np
from dataclasses import dataclass
from typing import Literal, Optional

@dataclass
class CalibrationPoint:
    x: float
    y: float
    head_h: float
    posture: str

class CalibratedPostureClassifier:
    def __init__(self, poly_degree: int = 2):
        self.poly_degree = poly_degree
        self._standing_curve = None
        self._sitting_curve = None
        self._standing_size_curve = None
        self._sitting_size_curve = None
        self._x_range = None

    def fit(self, calibration_points: list[CalibrationPoint]):
        standing = [p for p in calibration_points if p.posture == "standing"]
        sitting = [p for p in calibration_points if p.posture == "sitting"]

        if len(standing) < self.poly_degree + 1 or len(sitting) < self.poly_degree + 1:
            raise ValueError(
                f"Need at least {self.poly_degree + 1} calibration points per "
                f"class. Got {len(standing)} standing, {len(sitting)} sitting."
            )

        sx, sy = np.array([p.x for p in standing]), np.array([p.y for p in standing])
        tx, ty = np.array([p.x for p in sitting]), np.array([p.y for p in sitting])

        self._standing_curve = np.poly1d(np.polyfit(sx, sy, self.poly_degree))
        self._sitting_curve = np.poly1d(np.polyfit(tx, ty, self.poly_degree))

        s_h = np.array([p.head_h for p in standing])
        t_h = np.array([p.head_h for p in sitting])
        self._standing_size_curve = np.poly1d(np.polyfit(sx, s_h, self.poly_degree))
        self._sitting_size_curve = np.poly1d(np.polyfit(tx, t_h, self.poly_degree))

        all_x = np.concatenate([sx, tx])
        self._x_range = (all_x.min(), all_x.max())

    def classify(self, x1, y1, x2, y2, margin_px: float = 0.0):
        if self._standing_curve is None:
            raise RuntimeError("Call fit() before classify().")

        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        head_h = max(y2 - y1, 1e-6)

        cx_clamped = float(np.clip(cx, *self._x_range))

        y_stand_expected = self._standing_curve(cx_clamped)
        y_sit_expected = self._sitting_curve(cx_clamped)

        ref_head_h = float(np.clip(
            (self._standing_size_curve(cx_clamped) + self._sitting_size_curve(cx_clamped)) / 2.0,
            1e-6, None,
        ))

        dist_stand = abs(cy - y_stand_expected) / ref_head_h
        dist_sit = abs(cy - y_sit_expected) / ref_head_h

        if dist_stand < dist_sit - margin_px:
            posture = "standing"
        elif dist_sit < dist_stand - margin_px:
            posture = "sitting"
        else:
            posture = "standing" if dist_stand <= dist_sit else "sitting"

        return posture

class FurnitureZonePrior:
    def __init__(self, zones: list[tuple[list[tuple[float, float]], Optional[str]]]):
        self.zones = zones

    @staticmethod
    def _point_in_poly(x, y, poly) -> bool:
        n = len(poly)
        inside = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]
            xj, yj = poly[j]
            if ((yi > y) != (yj > y)) and (
                x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi
            ):
                inside = not inside
            j = i
        return inside

    def lookup(self, cx: float, cy: float) -> Optional[str]:
        for poly, implies in self.zones:
            if implies and self._point_in_poly(cx, cy, poly):
                return implies
        return None

class TemporalPostureSmoother:
    def __init__(self, y_threshold: float = 40.0):
        # Y-movement threshold (in pixels) required to allow a posture flip
        self.y_threshold = y_threshold
        # Stores {track_id: {"posture": "sitting", "cy": 150.0}}
        self._state = {}

    def update(self, track_id: int, raw_posture: str, cy: float, is_zone_override: bool = False) -> str:
        if track_id is None:
            return raw_posture
            
        weight = 3 if is_zone_override else 1
            
        # Initialize state for new tracks
        if track_id not in self._state:
            self._state[track_id] = {
                "posture": raw_posture, 
                "cy": cy,
                "history": [(raw_posture, weight)]
            }
            return raw_posture
            
        prev = self._state[track_id]
        
        # Keep history of last 15 raw predictions as (posture, weight)
        prev["history"].append((raw_posture, weight))
        if len(prev["history"]) > 15:
            prev["history"].pop(0)
            
        # 1. Soft-Lock Phase (Frames 1-15): 
        # Establish a highly accurate initial anchor using weighted majority voting.
        if len(prev["history"]) < 15:
            standing_votes = sum(w for p, w in prev["history"] if p == "standing")
            sitting_votes = sum(w for p, w in prev["history"] if p == "sitting")
            majority = "standing" if standing_votes >= sitting_votes else "sitting"
            prev["posture"] = majority
            # Update the anchor position smoothly
            prev["cy"] = (prev["cy"] * 0.8) + (cy * 0.2)
            return majority
            
        # 2. Hard-Lock Phase (Frame 15+):
        # Strict physical displacement check. Ignore minor math jitters, only flip if they physically moved.
        if raw_posture != prev["posture"]:
            if abs(cy - prev["cy"]) > self.y_threshold:
                # Legitimate large movement (e.g. actually standing up). Accept flip!
                prev["posture"] = raw_posture
                prev["cy"] = cy
            else:
                # Just mathematical boundary jitter. Reject the flip and keep old posture.
                pass
        else:
            # Posture agrees, gently update the reference Y to track slow legitimate movement
            prev["cy"] = (prev["cy"] * 0.8) + (cy * 0.2)
            
        return prev["posture"]
