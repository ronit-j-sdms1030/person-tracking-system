import numpy as np

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

    def process(self, keypoints: list) -> str:
        if not keypoints or len(keypoints) < 17:
            return "unknown"
            
        kpts = np.array(keypoints)
        
        # COCO indices: hip=11(L)/12(R), knee=13(L)/14(R), ankle=15(L)/16(R)
        l_hip, l_knee, l_ankle = kpts[11], kpts[13], kpts[15]
        r_hip, r_knee, r_ankle = kpts[12], kpts[14], kpts[16]
        
        def is_valid(*pts):
            return all(p[2] > self.CONF_THRESH for p in pts)

        angles = []
        if is_valid(l_hip, l_knee, l_ankle):
            angles.append(self._compute_angle(l_hip[:2], l_knee[:2], l_ankle[:2]))
        if is_valid(r_hip, r_knee, r_ankle):
            angles.append(self._compute_angle(r_hip[:2], r_knee[:2], r_ankle[:2]))
            
        if not angles:
            return "unknown"
            
        avg_angle = np.mean(angles)
        if avg_angle >= self.ANGLE_STANDING_MIN:
            return "standing"
        elif avg_angle <= self.ANGLE_SITTING_MAX:
            return "sitting"
        else:
            return "unknown"
