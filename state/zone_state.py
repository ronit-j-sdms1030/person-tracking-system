import time

class ZoneState:
    def __init__(self, zone_config: dict):
        self.zone_id = zone_config['zone_id']
        self.capacity_max = zone_config.get('capacity_max', 25)
        self.capacity_sitting_max = zone_config.get('capacity_sitting_max', 15)
        self.capacity_standing_max = zone_config.get('capacity_standing_max', 10)
        
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
            cam_cap = cam.get("capacity", self.capacity_max)
            self.camera_stats[cam_id] = {
                "camera_id": cam_id,
                "role": role,
                "capacity": cam_cap
            }
            if role in ["entry_exit", "both"]:
                self.camera_stats[cam_id]["entered_today"] = 0
                self.camera_stats[cam_id]["exited_today"] = 0
            if role in ["posture", "both"]:
                self.camera_stats[cam_id]["sitting"] = 0
                self.camera_stats[cam_id]["standing"] = 0
        
        self.track_timeout_seconds = 60.0 # Timeout for stale tracks (60s to prevent pause flickering)
        self.last_event_time = 0.0
        # Smoothing: only update occupancy when count is stable
        self._raw_occupancy = 0
        self._stable_occupancy = 0
        self._stable_count_streak = 0
        self.STABLE_STREAK_NEEDED = 10  # Require 10 consecutive frames (~0.5s) of stability before updating counts

    def update_camera_capacity(self, camera_id: str, capacity: int):
        if camera_id in self.camera_stats:
            self.camera_stats[camera_id]["capacity"] = capacity

    def reset_camera(self, camera_id: str):
        if camera_id in self.camera_stats:
            self.camera_stats[camera_id]["entered_today"] = 0
            self.camera_stats[camera_id]["exited_today"] = 0
            self.camera_stats[camera_id]["sitting"] = 0
            self.camera_stats[camera_id]["standing"] = 0
            self.camera_stats[camera_id]["_raw"] = 0
            self.camera_stats[camera_id]["_stable"] = 0
            self.camera_stats[camera_id]["_streak"] = 0
            
        stale_ids = [tid for tid, data in self.active_tracks.items() if data.get("camera_id") == camera_id]
        for tid in stale_ids:
            del self.active_tracks[tid]

    def update_capacity(self, capacity: int = None, capacity_sitting: int = None, capacity_standing: int = None):
        if capacity_sitting is not None:
            self.capacity_sitting_max = capacity_sitting
        if capacity_standing is not None:
            self.capacity_standing_max = capacity_standing
        if capacity is not None:
            self.capacity_max = capacity
            for stats in self.camera_stats.values():
                if "capacity" not in stats or stats["capacity"] is None:
                    stats["capacity"] = capacity

    def reset(self):
        self.entered_today = 0
        self.exited_today = 0
        self.active_tracks = {}
        self._raw_occupancy = 0
        self._stable_occupancy = 0
        self._stable_count_streak = 0
        for cam_id, stats in self.camera_stats.items():
            if "entered_today" in stats:
                stats["entered_today"] = 0
                stats["exited_today"] = 0
            if "sitting" in stats:
                stats["sitting"] = 0
                stats["standing"] = 0

    def _cleanup_stale_tracks(self, current_time: float):
        # Do not expire tracks if system is paused (no recent events within last 3 seconds)
        if self.last_event_time > 0 and (current_time - self.last_event_time) > 10.0:
            return
            
        stale_ids = [
            tid for tid, data in self.active_tracks.items()
            if current_time - data["timestamp"] > self.track_timeout_seconds
        ]
        for tid in stale_ids:
            del self.active_tracks[tid]

    def update_from_event(self, event: dict):
        current_time = event.get("timestamp", time.time())
        self.last_event_time = current_time
        self._cleanup_stale_tracks(current_time)
        
        ev_type = event.get("event")
        cam_id = event.get("camera_id")
        
        # Dynamically add camera to stats if it was uploaded after startup
        if cam_id and cam_id not in self.camera_stats:
            self.camera_stats[cam_id] = {
                "camera_id": cam_id,
                "role": "both",
                "capacity": self.capacity_max,
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
        raw = len(self.active_tracks)
        # Stabilise: only move the displayed count when we see the same raw value
        # for STABLE_STREAK_NEEDED consecutive reads (prevents per-frame bouncing)
        if raw == self._raw_occupancy:
            self._stable_count_streak += 1
        else:
            self._stable_count_streak = 0
        self._raw_occupancy = raw

        if self._stable_count_streak >= self.STABLE_STREAK_NEEDED or raw > self._stable_occupancy:
            # Accept increases immediately; only accept decreases when stable
            self._stable_occupancy = raw

        if self._stable_occupancy > 0:
            return self._stable_occupancy
        elif self.has_entry_exit_cams:
            return max(0, self.entered_today - self.exited_today)
        else:
            return 0

    @property
    def remaining_capacity(self) -> int:
        return max(0, self.capacity_max - self.current_occupancy)

    @property
    def remaining_sitting_capacity(self) -> int:
        return max(0, self.capacity_sitting_max - self.sitting_count)

    @property
    def remaining_standing_capacity(self) -> int:
        return max(0, self.capacity_standing_max - self.standing_count)

    @property
    def utilization_pct(self) -> float:
        if self.capacity_max == 0:
            return 0.0
        return round((self.current_occupancy / self.capacity_max) * 100, 1)

    @property
    def sitting_count(self) -> int:
        return sum(1 for data in self.active_tracks.values() if data.get("posture") == "sitting")

    @property
    def standing_count(self) -> int:
        return max(0, self.current_occupancy - self.sitting_count)

    def to_dict(self) -> dict:
        self._cleanup_stale_tracks(time.time())
        
        # Tally current posture and distinct occupancy per camera
        for cam_id, stats in self.camera_stats.items():
            cam_count = sum(1 for data in self.active_tracks.values() if data.get("camera_id") == cam_id)
            
            # Per-camera count smoothing
            if "_raw" not in stats:
                stats["_raw"] = 0
                stats["_stable"] = 0
                stats["_streak"] = 0
                
            if cam_count == stats["_raw"]:
                stats["_streak"] += 1
            else:
                stats["_streak"] = 0
            stats["_raw"] = cam_count
            
            if stats["_streak"] >= self.STABLE_STREAK_NEEDED or cam_count > stats["_stable"]:
                stats["_stable"] = cam_count
                
            display_count = stats["_stable"]
            
            cam_cap = stats.get("capacity", self.capacity_max)
            stats["capacity"] = cam_cap
            stats["current_occupancy"] = display_count
            stats["remaining_capacity"] = max(0, cam_cap - display_count)
            if "sitting" in stats:
                stats["sitting"] = 0
                stats["standing"] = 0
                
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
            "capacity_sitting_max": self.capacity_sitting_max,
            "capacity_standing_max": self.capacity_standing_max,
            "entered_today": self.entered_today,
            "exited_today": self.exited_today,
            "current_occupancy": self.current_occupancy,
            "remaining_capacity": self.remaining_capacity,
            "remaining_sitting_capacity": self.remaining_sitting_capacity,
            "remaining_standing_capacity": self.remaining_standing_capacity,
            "utilization_pct": self.utilization_pct,
            "sitting_count": self.sitting_count,
            "standing_count": self.standing_count,
            "cameras": list(self.camera_stats.values())
        }
