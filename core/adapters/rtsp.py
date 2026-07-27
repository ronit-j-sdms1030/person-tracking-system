import cv2
import time
import logging
from typing import Optional
import numpy as np
from core.adapters.base import CameraSource

logger = logging.getLogger(__name__)

class RTSPSource(CameraSource):
    def __init__(self, camera_id: str, source: str):
        super().__init__(camera_id, source)
        self.cap = cv2.VideoCapture(self.source)
        self.max_retries = 3
        self.retry_delay = 1.0 # seconds
        if not self.cap.isOpened():
            logger.warning(f"Failed to open source {self.source} for camera {self.camera_id} initially.")

    def _reconnect(self):
        logger.info(f"Attempting to reconnect to {self.source} for camera {self.camera_id}")
        if self.cap:
            self.cap.release()
        for i in range(self.max_retries):
            self.cap = cv2.VideoCapture(self.source)
            if self.cap.isOpened():
                logger.info(f"Successfully reconnected to {self.source}")
                return True
            time.sleep(self.retry_delay)
        logger.error(f"Failed to reconnect after {self.max_retries} attempts.")
        return False

    def read_frame(self) -> Optional[np.ndarray]:
        if not self.is_open():
            if not self._reconnect():
                return None
        
        ret, frame = self.cap.read()
        if not ret:
            logger.warning(f"Dropped frame or stream ended on camera {self.camera_id}.")
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
