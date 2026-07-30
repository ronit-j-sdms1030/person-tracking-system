import cv2
from ultralytics import YOLO

model = YOLO("best_posture.pt")
cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()

results = model(frame, conf=0.1) # very low conf
boxes = results[0].boxes
print(f"Total posture boxes at conf 0.1: {len(boxes) if boxes else 0}")
if boxes:
    print(boxes.conf.cpu().numpy())
