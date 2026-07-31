import cv2
from ultralytics import RTDETR

model = RTDETR("yoloh.pt")

# resolve class id for head
head_cls = 0
for idx, name in model.names.items():
    if "head" in name.lower():
        head_cls = idx
        break

cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
frames_to_test = [100, 500, 1000]

thresholds = [0.30, 0.40, 0.50, 0.60, 0.70]

for frame_idx in frames_to_test:
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    if not ret:
        continue
    
    print(f"\n--- Frame {frame_idx} ---")
    results = model.predict(frame, classes=[head_cls], imgsz=640, verbose=False, conf=0.1) # run with low conf to get all
    boxes = results[0].boxes
    if boxes is None:
        print("No detections.")
        continue
        
    confs = boxes.conf.cpu().numpy()
    
    for t in thresholds:
        count = sum(c >= t for c in confs)
        print(f"Threshold {t:.2f} -> {count} heads detected")

