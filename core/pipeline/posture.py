import logging

logger = logging.getLogger(__name__)

class PostureLogic:
    CONF_THRESH = 0.5
    ANGLE_STANDING_MIN = 150 # Leg relatively straight
    ANGLE_SITTING_MAX = 130  # Leg noticeably bent

    def __init__(self):
        pass

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
        enable_back_row_rule: bool = False,
        back_row_y1_max: float = 105.0,
        back_row_y2_max: float = 260.0,
        back_row_x1_min: float = 330.0,
    ) -> str:
        # Calculate aspect ratio of bounding box if available
        ar = None
        if bbox is not None and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            width = x2 - x1
            height = y2 - y1
            if height > 0:
                ar = width / height

            # Configurable Back-row standing check for desk/table occlusions:
            if enable_back_row_rule and (y1 < back_row_y1_max) and (y2 < back_row_y2_max) and (x1 > back_row_x1_min):
                if class_id != 0 or (ar is not None and ar < 0.65):
                    logger.debug(f"[track_{track_id}] posture=standing | signal=BACK_ROW_OCCLUSION_RULE | class_id={class_id} | ar={round(ar, 2) if ar else None} | bbox={bbox}")
                    return "standing"

        signal = "DEFAULT_SITTING"
        posture = "sitting"

        # 1. Model Predicted Class ID with Geometry Safety Overrides
        if class_id is not None:
            if class_id == 1:
                if ar is not None and ar > 0.78:
                    posture = "sitting"
                    signal = "MODEL_STANDING_OVERRIDDEN_BY_WIDE_AR"
                else:
                    posture = "standing"
                    signal = "MODEL_CLASS_STANDING"
            elif class_id == 0:
                if ar is not None and ar < 0.45:
                    posture = "standing"
                    signal = "MODEL_SITTING_OVERRIDDEN_BY_TALL_AR"
                else:
                    posture = "sitting"
                    signal = "MODEL_CLASS_SITTING"
        # 2. Pure Geometry Aspect Ratio Fallback
        elif ar is not None:
            if ar < 0.58:
                posture = "standing"
                signal = "GEOMETRY_ASPECT_RATIO_TALL"
            else:
                posture = "sitting"
                signal = "GEOMETRY_ASPECT_RATIO_WIDE"

        logger.debug(f"[track_{track_id}] posture={posture} | signal={signal} | class_id={class_id} | ar={round(ar, 2) if ar else None}")
        return posture

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
