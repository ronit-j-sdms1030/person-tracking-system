import cv2
from core.pipeline.detector import Detector

detector = Detector(model_path="yoloh.pt", conf_thresh=0.66)

cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()

if ret:
    detections = detector._detect_or_track(frame, track=False)
    print(f"Total head detections: {len(detections)}")
    sitting = sum(1 for d in detections if d.get('posture_state') == 0)
    standing = sum(1 for d in detections if d.get('posture_state') == 1)
    unknown = sum(1 for d in detections if d.get('posture_state') is None)
    print(f"Sitting: {sitting}, Standing: {standing}, Unknown: {unknown}")
else:
    print("Could not read frame.")
