import cv2
import logging
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
        self.cap = cv2.VideoCapture(self.source)
        if not self.cap.isOpened():
            logger.error(f"[{camera_id}] Cannot open file: {self.source}")

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.is_open():
            return None
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
