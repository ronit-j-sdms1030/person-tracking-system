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
        
        # Initialize per-camera tracking stats
        self.camera_stats = {}
        for cam in zone_config.get("cameras", []):
            cam_id = cam["camera_id"]
            role = cam.get("role", "entry_exit")
            self.camera_stats[cam_id] = {
                "camera_id": cam_id,
                "role": role
            }
            if role in ["entry_exit", "both"]:
                self.camera_stats[cam_id]["entered_today"] = 0
                self.camera_stats[cam_id]["exited_today"] = 0
            if role in ["posture", "both"]:
                self.camera_stats[cam_id]["sitting"] = 0
                self.camera_stats[cam_id]["standing"] = 0
        
        self.track_timeout_seconds = 5.0 # Timeout for stale tracks

    def reset(self):
        self.entered_today = 0
        self.exited_today = 0
        self.active_tracks = {}
        for cam_id, stats in self.camera_stats.items():
            if "entered_today" in stats:
                stats["entered_today"] = 0
                stats["exited_today"] = 0
            if "sitting" in stats:
                stats["sitting"] = 0
                stats["standing"] = 0

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
        cam_id = event.get("camera_id")
        
        # Dynamically add camera to stats if it was uploaded after startup
        if cam_id and cam_id not in self.camera_stats:
            # We don't know the exact role, but we can enable all stats fields just in case
            self.camera_stats[cam_id] = {
                "camera_id": cam_id,
                "role": "both",
                "entered_today": 0,
                "exited_today": 0,
                "sitting": 0,
                "standing": 0
            }
        
        if ev_type == "entered":
            self.entered_today += 1
            if cam_id in self.camera_stats and "entered_today" in self.camera_stats[cam_id]:
                self.camera_stats[cam_id]["entered_today"] += 1
        elif ev_type == "exited":
            self.exited_today += 1
            if cam_id in self.camera_stats and "exited_today" in self.camera_stats[cam_id]:
                self.camera_stats[cam_id]["exited_today"] += 1
            
        track_id = event.get("track_id")
        posture = event.get("posture")
        
        # Track posture changes for the specific camera
        if posture and cam_id in self.camera_stats and "sitting" in self.camera_stats[cam_id]:
            # This is a naive increment; in reality you'd track the track_id's state and delta it.
            # But for simple stats/demo matching Claude's logic, we will just recount below in to_dict 
            pass
        
        if track_id is not None:
            if ev_type == "exited":
                if track_id in self.active_tracks:
                    del self.active_tracks[track_id]
            else:
                self.active_tracks[track_id] = {
                    "timestamp": current_time,
                    "posture": posture if posture else "unknown",
                    "camera_id": cam_id
                }

    @property
    def current_occupancy(self) -> int:
        if self.active_tracks:
            return len(self.active_tracks)
        elif self.has_entry_exit_cams:
            return max(0, self.entered_today - self.exited_today)
        else:
            return 0

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
        
        # Reset sitting/standing per camera
        for cam_id, stats in self.camera_stats.items():
            if "sitting" in stats:
                stats["sitting"] = 0
                stats["standing"] = 0
                
        # Tally current posture per camera
        for track_id, data in self.active_tracks.items():
            cam_id = data.get("camera_id")
            posture = data.get("posture")
            if cam_id in self.camera_stats and "sitting" in self.camera_stats[cam_id]:
                if posture == "sitting":
                    self.camera_stats[cam_id]["sitting"] += 1
                elif posture == "standing":
                    self.camera_stats[cam_id]["standing"] += 1

        return {
            "zone_id": self.zone_id,
            "capacity_max": self.capacity_max,
            "entered_today": self.entered_today,
            "exited_today": self.exited_today,
            "current_occupancy": self.current_occupancy,
            "remaining_capacity": self.remaining_capacity,
            "utilization_pct": self.utilization_pct,
            "sitting_count": self.sitting_count,
            "standing_count": self.standing_count,
            "cameras": list(self.camera_stats.values())
        }
