import cv2
from ultralytics import YOLO

cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 500)
ret, frame = cap.read()

print("=== Analyzing best.pt Body Boxes (Class 1) ===")
m_best = YOLO('best.pt')
results = m_best(frame, verbose=False)
for r in results:
    for box in r.boxes:
        cls_id = int(box.cls[0])
        if cls_id == 1: # Person body
            x1, y1, x2, y2 = map(float, box.xyxy[0])
            w = x2 - x1
            h = y2 - y1
            cx = x1 + w/2
            cy = y1 + h/2
            ratio = h / w if w > 0 else 0
            print(f"Center: ({cx:5.1f}, {cy:5.1f}) | W: {w:5.1f} | H: {h:5.1f} | H/W Ratio: {ratio:.2f}")
