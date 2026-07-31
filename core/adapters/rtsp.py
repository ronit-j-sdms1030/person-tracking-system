import cv2
import time
import os
import threading
import logging
from typing import Optional
import numpy as np
from core.adapters.base import CameraSource

logger = logging.getLogger(__name__)

class RTSPSource(CameraSource):
    """
    Threaded RTSP Stream Reader for zero-latency live streams.
    Runs a dedicated thread to continuously pull raw frames from OpenCV FFMPEG buffer,
    always keeping ONLY the most recent frame. This completely eliminates buffer lag.
    """
    def __init__(self, camera_id: str, source: str):
        super().__init__(camera_id, source)
        self.max_retries = 5
        self.retry_delay = 2.0
        self.latest_frame = None
        self.running = True
        self.lock = threading.Lock()
        self.cap = self._open()
        
        # Start dedicated frame-grabber background thread
        self.thread = threading.Thread(target=self._update_loop, name=f"rtsp-grab-{camera_id}", daemon=True)
        self.thread.start()

    def _open(self):
        os.environ["OPENCV_FFMPEG_LOGLEVEL"] = "-8"
        os.environ["OPENCV_LOG_LEVEL"] = "FATAL"
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|buffer_size;2097152|max_delay;500000|fflags;nobuffer"
        cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        return cap

    def _update_loop(self):
        while self.running:
            if not self.cap or not self.cap.isOpened():
                time.sleep(1.0)
                continue
            ret, frame = self.cap.read()
            if ret and frame is not None:
                with self.lock:
                    self.latest_frame = frame
            else:
                time.sleep(0.02)

    def read_frame(self) -> Optional[np.ndarray]:
        with self.lock:
            if self.latest_frame is not None:
                frame = self.latest_frame.copy()
                return frame
        return None

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def set_position(self, percent: float) -> None:
        pass

    def release(self) -> None:
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
