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

    def process(self, keypoints: list, bbox: list = None) -> str:
        # First try to use keypoints if available and confident
        pose_result = "unknown"
        if keypoints and len(keypoints) >= 17:
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
                
            if angles:
                avg_angle = np.mean(angles)
                if avg_angle >= self.ANGLE_STANDING_MIN:
                    pose_result = "standing"
                elif avg_angle <= self.ANGLE_SITTING_MAX:
                    pose_result = "sitting"
        
        # If keypoints failed (e.g. legs occluded by seats), use bounding box aspect ratio
        if pose_result == "unknown" and bbox and len(bbox) == 4:
            x1, y1, x2, y2 = bbox
            width = x2 - x1
            height = y2 - y1
            if height > 0:
                aspect_ratio = width / height
                # A squarish or wide box usually indicates sitting, 
                # a tall box indicates standing
                if aspect_ratio > 0.75:
                    pose_result = "sitting"
                else:
                    pose_result = "standing"
                    
        return pose_result
