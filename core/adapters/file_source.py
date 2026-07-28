import cv2
import logging
import threading
from typing import Optional
import numpy as np
from core.adapters.base import CameraSource

logger = logging.getLogger(__name__)


class FileSource(CameraSource):
    """
    Reads from a local video file. Does NOT reconnect on EOF — returns None
    when the video ends, which signals the camera loop to stop.
    Use this for Stage 1 testing with .mp4 / .avi / etc.
    """

    def __init__(self, camera_id: str, source: str):
        super().__init__(camera_id, source)
        self._lock = threading.Lock()
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"[{camera_id}] Cannot open file: {self.source}")

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.is_open():
            return None
        with self._lock:
            ret, frame = self.cap.read()
        if not ret:
            logger.info(f"[{self.camera_id}] End of file: {self.source}")
            return None
        return frame

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None

    def set_position(self, percent: float) -> None:
        if not self.is_open():
            return
        with self._lock:
            total_frames = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
            if total_frames > 0:
                target_frame = int(total_frames * (max(0.0, min(100.0, percent)) / 100.0))
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, target_frame)

    def get_position(self) -> float:
        if not self.is_open():
            return 0.0
        with self._lock:
            pos = self.cap.get(cv2.CAP_PROP_POS_FRAMES)
            total = self.cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if total > 0:
            return round((pos / total) * 100.0, 2)
        return 0.0
