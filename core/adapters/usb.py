import cv2
import time
import logging
from typing import Optional
import numpy as np
from core.adapters.base import CameraSource

logger = logging.getLogger(__name__)


class USBSource(CameraSource):
    """
    Reads from a USB/webcam device. source can be:
      - An integer index string: "0", "1", etc.  → cv2.VideoCapture(int)
      - A device path string: "/dev/video0"      → cv2.VideoCapture(str)
    Use this for Stage 3 live camera testing.
    """

    def __init__(self, camera_id: str, source: str):
        super().__init__(camera_id, source)
        # Convert "0", "1" etc. to int device index; keep paths as-is
        try:
            device = int(source)
        except ValueError:
            device = source

        self.device = device
        self.max_retries = 5
        self.retry_delay = 2.0
        self.cap = cv2.VideoCapture(self.device)
        if not self.cap.isOpened():
            logger.warning(f"[{camera_id}] Failed to open USB device: {source}")

    def _reconnect(self) -> bool:
        logger.info(f"[{self.camera_id}] Reconnecting to USB device: {self.device}")
        if self.cap:
            self.cap.release()
        for i in range(self.max_retries):
            self.cap = cv2.VideoCapture(self.device)
            if self.cap.isOpened():
                logger.info(f"[{self.camera_id}] USB reconnected on attempt {i+1}")
                return True
            logger.warning(f"[{self.camera_id}] Retry {i+1}/{self.max_retries}...")
            time.sleep(self.retry_delay)
        logger.error(f"[{self.camera_id}] USB device unreachable after {self.max_retries} retries.")
        return False

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.is_open():
            if not self._reconnect():
                return None

        ret, frame = self.cap.read()
        if not ret:
            logger.warning(f"[{self.camera_id}] Dropped USB frame, attempting reconnect...")
            if not self._reconnect():
                return None
            ret, frame = self.cap.read()
            if not ret:
                return None
        return frame

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def release(self) -> None:
        if self.cap:
            self.cap.release()
            self.cap = None
