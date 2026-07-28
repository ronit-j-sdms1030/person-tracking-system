from abc import ABC, abstractmethod
import numpy as np
from typing import Optional

class CameraSource(ABC):
    def __init__(self, camera_id: str, source: str):
        self.camera_id = camera_id
        self.source = source

    @abstractmethod
    def read_frame(self) -> Optional[np.ndarray]:
        pass

    @abstractmethod
    def is_open(self) -> bool:
        pass

    @abstractmethod
    def release(self) -> None:
        pass

    @abstractmethod
    def set_position(self, percent: float) -> None:
        """Seek to a percentage of the stream (0.0 to 100.0)"""
        pass

    def get_position(self) -> float:
        """Return current position as percentage (0.0 to 100.0). Default: 0"""
        return 0.0
