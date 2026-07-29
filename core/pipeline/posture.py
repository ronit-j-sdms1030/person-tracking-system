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
        
        fh = frame_shape[0] if (frame_shape and len(frame_shape) >= 2 and frame_shape[0] > 0) else 720
        fw = frame_shape[1] if (frame_shape and len(frame_shape) >= 2 and frame_shape[1] > 0) else 1280

        if bbox is not None and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            width = x2 - x1
            height = y2 - y1
            if height > 0:
                ar = width / height
            norm_y1 = y1 / fh
            norm_y2 = y2 / fh
            norm_h = height / fh

            # 1. Camera-Specific Manual ROI Rules (if explicitly configured for specialized cameras)
            if enable_standing_aisle_roi and (x1 > standing_aisle_x1_min or (x1 + x2)/2 > standing_aisle_x1_min):
                logger.debug(f"[track_{track_id}] posture=standing | signal=DOORWAY_AISLE_ROI_STANDING")
                return "standing"

            if enable_back_desk_roi and (y1 < back_desk_y1_max) and (y2 < back_desk_y2_max) and (x1 > back_desk_x1_min):
                logger.debug(f"[track_{track_id}] posture=standing | signal=BACK_DESK_SPATIAL_ROI_OCCLUSION_RULE")
                return "standing"

        # 2. Universal Multi-Signal Posture Evaluator (Works across all environments: Bus, Office, Classroom)
        signal = "DEFAULT_SITTING"
        posture = "sitting"

        # Standalone Head Box Fallback (If no body box was matched and only head box exists):
        if norm_h < 0.26:
            logger.debug(f"[track_{track_id}] posture=sitting | signal=STANDALONE_HEAD_BOX_SITTING")
            return "sitting"

        # Signal A: Full-Height Standing Body (Person standing upright in room/aisle)
        if norm_h > 0.52 or (ar is not None and ar < 0.28):
            posture = "standing"
            signal = "FULL_HEIGHT_STANDING"
        # Signal B: Universal Furniture-Occluded Standing Body (Person standing behind desk/table/counter)
        elif (norm_y1 < 0.25) and (norm_y2 < 0.48) and (norm_h < 0.32) and (ar is not None and ar < 0.65):
            posture = "standing"
            signal = "UNIVERSAL_DESK_OCCLUDED_STANDING"
        # Signal C: Model Class ID with Aspect Ratio Bounds
        elif class_id == 1 and (ar is None or ar < 0.65):
            posture = "standing"
            signal = "MODEL_CLASS_STANDING"
        elif class_id == 0:
            if ar is not None and ar < 0.30:
                posture = "standing"
                signal = "MODEL_SITTING_OVERRIDDEN_BY_EXTREMELY_TALL_AR"
            else:
                posture = "sitting"
                signal = "MODEL_CLASS_SITTING"
        elif ar is not None:
            if ar < 0.35:
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
