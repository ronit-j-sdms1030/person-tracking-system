import time

class ZoneState:
    def __init__(self, zone_config: dict):
        self.zone_id = zone_config['zone_id']
        self.capacity_max = zone_config['capacity_max']
        
        self.entered_today = 0
        self.exited_today = 0
        
        # track_id -> {"timestamp": ts, "posture": "sitting"|"standing"|"unknown"}
        self.active_tracks = {}
        
        # Determine if this zone uses entry/exit logic or posture only for occupancy
        self.has_entry_exit_cams = any(
            cam.get("role") in ["entry_exit", "both"]
            for cam in zone_config.get("cameras", [])
        )
        
        self.track_timeout_seconds = 5.0 # Timeout for stale tracks

    def _cleanup_stale_tracks(self, current_time: float):
        stale_ids = [
            tid for tid, data in self.active_tracks.items()
            if current_time - data["timestamp"] > self.track_timeout_seconds
        ]
        for tid in stale_ids:
            del self.active_tracks[tid]

    def update_from_event(self, event: dict):
        current_time = event.get("timestamp", time.time())
        self._cleanup_stale_tracks(current_time)
        
        ev_type = event.get("event")
        if ev_type == "entered":
            self.entered_today += 1
        elif ev_type == "exited":
            self.exited_today += 1
            
        track_id = event.get("track_id")
        posture = event.get("posture")
        
        if track_id is not None:
            if ev_type == "exited":
                if track_id in self.active_tracks:
                    del self.active_tracks[track_id]
            else:
                self.active_tracks[track_id] = {
                    "timestamp": current_time,
                    "posture": posture if posture else "unknown"
                }

    @property
    def current_occupancy(self) -> int:
        if self.has_entry_exit_cams:
            return max(0, self.entered_today - self.exited_today)
        else:
            return len(self.active_tracks)

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.capacity_max - self.current_occupancy)

    @property
    def utilization_pct(self) -> float:
        if self.capacity_max == 0:
            return 0.0
        return round((self.current_occupancy / self.capacity_max) * 100, 1)

    @property
    def sitting_count(self) -> int:
        return sum(1 for data in self.active_tracks.values() if data["posture"] == "sitting")

    @property
    def standing_count(self) -> int:
        return sum(1 for data in self.active_tracks.values() if data["posture"] == "standing")

    def to_dict(self) -> dict:
        self._cleanup_stale_tracks(time.time())
        return {
            "zone_id": self.zone_id,
            "capacity_max": self.capacity_max,
            "entered_today": self.entered_today,
            "exited_today": self.exited_today,
            "current_occupancy": self.current_occupancy,
            "remaining_capacity": self.remaining_capacity,
            "utilization_pct": self.utilization_pct,
            "sitting_count": self.sitting_count,
            "standing_count": self.standing_count
        }
