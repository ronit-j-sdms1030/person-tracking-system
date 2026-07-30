import cv2
from core.pipeline.detector import Detector

detector = Detector(model_path="yoloh.pt", conf_thresh=0.66)

cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()

detections = detector._detect_or_track(frame, track=True)
for d in detections:
    hx1, hy1, hx2, hy2 = d["bbox"]
    cx = (hx1 + hx2) / 2
    cy = (hy1 + hy2) / 2
    h = hy2 - hy1
    print(f"Post: {d['posture_state']:8s} | CX: {cx:6.1f} | CY: {cy:6.1f} | H: {h:5.1f}")
