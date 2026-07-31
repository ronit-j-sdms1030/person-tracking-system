import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Tunable constants (adjust during Day-2 validation)
# ─────────────────────────────────────────────────────────────────────────────
FRAMES_TO_CONFIRM_EXIT = 6  # track must be ABSENT this many consecutive frames
                              # before "exited" fires — updates occupancy quickly
COOLDOWN_SECONDS       = 1.0 # minimum seconds before the same track_id can fire
                              # another event (overridden by cam config if present)


class EntryExitLogic:
    """
    Frame-presence based entry/exit detection.

    Rules:
      - ENTERED: a track_id appears in the frame for the first time.
      - EXITED:  a track_id is absent for FRAMES_TO_CONFIRM_EXIT consecutive
                 frames (debounce against occlusion / missed detections).
      - Cooldown: a track_id cannot re-fire the same event within
                  cooldown_seconds (guards against ID re-use edge cases).

    Requires NO line, NO direction_in, NO cooldown_px in config.
    """

    def __init__(self, config: Dict[str, Any]):
        self.cooldown_seconds = float(
            config.get("cooldown_seconds", COOLDOWN_SECONDS)
        )

        # track_id → last frame index it was seen
        self._active: Dict[int, int] = {}

        # track_id → how many consecutive frames it has been absent
        self._absent_count: Dict[int, int] = {}

        # track_id → timestamp of its last fired event (for cooldown)
        self._last_event_time: Dict[int, float] = {}

        self._frame_index: int = 0

    # ── public API ────────────────────────────────────────────────────────────

    def process_frame(
        self,
        detections: List[Dict[str, Any]],
        current_time: float,
    ) -> Dict[int, str]:
        """
        Call once per processed frame with the full list of detections
        (from the tracker) for this camera.

        Returns a dict  {track_id: "entered" | "exited"}  for tracks that
        fired an event this frame.  Empty dict = no events this frame.
        """
        self._frame_index += 1
        events: Dict[int, str] = {}

        current_ids = {
            d["track_id"]
            for d in detections
            if d.get("track_id") is not None
        }

        # ── 1. New tracks → "entered" ─────────────────────────────────────
        for tid in current_ids:
            if tid not in self._active:
                if self._cooldown_ok(tid, current_time):
                    events[tid] = "entered"
                    self._last_event_time[tid] = current_time
                    logger.info(f"[entry_exit] track {tid} ENTERED (new in frame)")
            # Either way, mark as active and clear absence counter
            self._active[tid] = self._frame_index
            self._absent_count.pop(tid, None)

        # ── 2. Missing tracks → accumulate absence, then "exited" ─────────
        gone_ids = set(self._active.keys()) - current_ids
        for tid in gone_ids:
            self._absent_count[tid] = self._absent_count.get(tid, 0) + 1

            if self._absent_count[tid] >= FRAMES_TO_CONFIRM_EXIT:
                if self._cooldown_ok(tid, current_time):
                    events[tid] = "exited"
                    self._last_event_time[tid] = current_time
                    logger.info(
                        f"[entry_exit] track {tid} EXITED "
                        f"(absent {self._absent_count[tid]} frames)"
                    )
                # Remove from active regardless of cooldown
                del self._active[tid]
                self._absent_count.pop(tid, None)

        return events

    # ── helpers ───────────────────────────────────────────────────────────────

    def _cooldown_ok(self, tid: int, current_time: float) -> bool:
        last = self._last_event_time.get(tid, 0.0)
        return (current_time - last) >= self.cooldown_seconds
