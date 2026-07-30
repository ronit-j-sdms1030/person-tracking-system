import cv2
cap = cv2.VideoCapture("data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4")
ret, frame = cap.read()
if ret:
    print(f"Original Frame Size: {frame.shape[1]}x{frame.shape[0]}")
