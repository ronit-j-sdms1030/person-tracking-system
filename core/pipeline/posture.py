import logging

logger = logging.getLogger(__name__)

class PostureLogic:
    CONF_THRESH = 0.5
    ANGLE_STANDING_MIN = 150 # Leg relatively straight
    ANGLE_SITTING_MAX = 130  # Leg noticeably bent

    # User-Specified Calibrated Tuning Thresholds:
    FURNITURE_Y_BOUNDARY = 180.0  # Y = 180 boundary line (heads below Y=180 flagged as sitting)
    MATH_CURVE_MARGIN = -0.2      # Curve margin penalty
    HYSTERESIS_DELTA_Y = 40.0     # 40px vertical movement hysteresis threshold

    def __init__(self):
        self.track_state = {}     # track_id -> {'last_cy': float, 'posture': str}

    def _compute_angle(self, p1, p2, p3):
        v1 = p1 - p2
        v2 = p3 - p2
        cos_theta = np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-6)
        angle = np.degrees(np.arccos(np.clip(cos_theta, -1.0, 1.0)))
        return angle

    def process(
        self,
        keypoints: list = None,
        bbox: list = None,
        class_id: int = None,
        track_id: str = None,
        frame_shape: tuple = None,
        enable_back_desk_roi: bool = False,
        back_desk_y1_max: float = 110.0,
        back_desk_y2_max: float = 260.0,
        back_desk_x1_min: float = 330.0,
        enable_standing_aisle_roi: bool = False,
        standing_aisle_x1_min: float = 800.0,
    ) -> str:
        ar = None
        norm_y1, norm_y2, norm_h = 0.0, 0.0, 0.0
        cy = 0.0
        
        fh = frame_shape[0] if (frame_shape and len(frame_shape) >= 2 and frame_shape[0] > 0) else 576
        fw = frame_shape[1] if (frame_shape and len(frame_shape) >= 2 and frame_shape[1] > 0) else 1024

        if bbox is not None and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            width = x2 - x1
            height = y2 - y1
            cy = (y1 + y2) / 2.0
            if height > 0:
                ar = width / height
            norm_y1 = y1 / fh
            norm_y2 = y2 / fh
            norm_h = height / fh

            # 1. Furniture Zone Boundary Rule: Y = 180 (Head located below 180px line -> Sitting)
            if cy >= (self.FURNITURE_Y_BOUNDARY + (self.MATH_CURVE_MARGIN * 10)):
                raw_posture = "sitting"
            else:
                raw_posture = "standing"

            # 2. Physical Hysteresis Movement Rule: Must move vertically by > 40px to flip posture
            if track_id is not None:
                t_key = str(track_id)
                if t_key in self.track_state:
                    prev_state = self.track_state[t_key]
                    prev_cy = prev_state.get('last_cy', cy)
                    prev_posture = prev_state.get('posture', raw_posture)

                    if abs(cy - prev_cy) < self.HYSTERESIS_DELTA_Y and raw_posture != prev_posture:
                        # Lock in previous posture until 40px physical movement threshold is exceeded
                        raw_posture = prev_posture

                    self.track_state[t_key] = {'last_cy': cy, 'posture': raw_posture}
                else:
                    self.track_state[t_key] = {'last_cy': cy, 'posture': raw_posture}

            return raw_posture

        # 3. Keypoints Pose Fallback
        if keypoints and len(keypoints) >= 17:
            kpts = np.array(keypoints)
            l_hip, l_knee, l_ankle = kpts[11], kpts[13], kpts[15]
            r_hip, r_knee, r_ankle = kpts[12], kpts[14], kpts[16]
            
            def is_valid(*pts):
                return all(p[2] > self.CONF_THRESH for p in pts)

            angles = []
            if is_valid(l_hip, l_knee, l_ankle):
                angles.append(self._compute_angle(l_hip[:2], l_knee[:2], l_ankle[:2]))
            if is_valid(r_hip, r_knee, r_ankle):
                angles.append(self._compute_angle(r_hip[:2], r_knee[:2], r_ankle[:2]))
                
            if angles:
                avg_angle = np.mean(angles)
                if avg_angle >= self.ANGLE_STANDING_MIN:
                    return "standing"
                elif avg_angle <= self.ANGLE_SITTING_MAX:
                    return "sitting"

        return "sitting"
