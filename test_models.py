import cv2
from ultralytics import YOLO

cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()
if not ret:
    print("Could not read frame")
    exit()

print("=== Testing best_posture.pt ===")
try:
    m_posture = YOLO('best_posture.pt')
    results = m_posture(frame, verbose=False)
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            print(f"Class: {cls_id} | Conf: {conf:.2f} | Center: ({cx:.1f}, {cy:.1f})")
except Exception as e:
    print("Error with best_posture.pt:", e)

print("\n=== Testing best.pt ===")
try:
    m_best = YOLO('best.pt')
    results = m_best(frame, verbose=False)
    for r in results:
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            print(f"Class: {cls_id} ({m_best.names[cls_id]}) | Conf: {conf:.2f} | Center: ({cx:.1f}, {cy:.1f})")
except Exception as e:
    print("Error with best.pt:", e)
