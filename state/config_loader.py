import yaml
import os

class ConfigLoader:
    def __init__(self, config_path: str = "config/site_config.yaml"):
        self.config_path = config_path
        self.site_id = None
        self.zones = []
        self.raw_data = None

    def load_and_validate(self):
        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Config file not found: {self.config_path}")
        
        with open(self.config_path, "r") as f:
            data = yaml.safe_load(f)
            
        if not data:
            raise ValueError("Config file is empty.")
            
        self.site_id = data.get("site_id")
        if not self.site_id:
            raise ValueError("Missing 'site_id' in config.")
            
        self.zones = data.get("zones")
        if not self.zones or not isinstance(self.zones, list):
            raise ValueError("Missing or invalid 'zones' in config.")
            
        for zone in self.zones:
            if "zone_id" not in zone:
                raise ValueError("Zone missing 'zone_id'.")
            if "capacity_max" not in zone:
                raise ValueError(f"Zone {zone['zone_id']} missing 'capacity_max'.")
            
            cameras = zone.get("cameras")
            if cameras is None or not isinstance(cameras, list):
                raise ValueError(f"Zone {zone['zone_id']} missing or invalid 'cameras'.")
                
            for cam in cameras:
                if "camera_id" not in cam:
                    raise ValueError(f"Camera in zone {zone['zone_id']} missing 'camera_id'.")
                if "role" not in cam:
                    raise ValueError(f"Camera {cam['camera_id']} missing 'role'.")
                    
        self.raw_data = data
        return data

    def add_camera(self, camera_id: str, source: str, role: str, adapter: str = "file"):
        if not self.raw_data:
            # Load raw data directly without triggering full validation
            with open(self.config_path, "r") as f:
                self.raw_data = yaml.safe_load(f)
            # Ensure cameras list exists
            if self.raw_data["zones"][0].get("cameras") is None:
                self.raw_data["zones"][0]["cameras"] = []
            
        zone = self.raw_data["zones"][0]

        # prevent duplicate camera_id by updating instead
        existing = next((c for c in zone["cameras"] if c["camera_id"] == camera_id), None)
        if existing:
            existing["source"] = source
            existing["role"] = role
            existing["adapter"] = adapter
            self._save()
            return existing

        new_cam = {
            "camera_id": camera_id,
            "adapter": adapter,
            "source": source,
            "role": role,
            "frame_skip": 1,
        }

        if role in ("entry_exit", "both"):
            new_cam["cooldown_seconds"] = 2.0

        zone["cameras"].append(new_cam)
        self._save()
        return new_cam

    def remove_camera(self, camera_id: str) -> bool:
        if not self.raw_data:
            with open(self.config_path, "r") as f:
                self.raw_data = yaml.safe_load(f)
            if self.raw_data["zones"][0].get("cameras") is None:
                self.raw_data["zones"][0]["cameras"] = []
                
        zone = self.raw_data["zones"][0]
        original_len = len(zone["cameras"])
        zone["cameras"] = [c for c in zone["cameras"] if c["camera_id"] != camera_id]
        if len(zone["cameras"]) < original_len:
            self._save()
            return True
        return False

    def update_capacity(self, capacity: int = None, capacity_sitting: int = None, capacity_standing: int = None):
        if not self.raw_data:
            with open(self.config_path, "r") as f:
                self.raw_data = yaml.safe_load(f)
        
        zone = self.raw_data["zones"][0]
        if capacity_sitting is not None:
            zone["capacity_sitting_max"] = capacity_sitting
        if capacity_standing is not None:
            zone["capacity_standing_max"] = capacity_standing
        if capacity is not None:
            zone["capacity_max"] = capacity
        elif capacity_sitting is not None or capacity_standing is not None:
            zone["capacity_max"] = (zone.get("capacity_sitting_max", 15) + zone.get("capacity_standing_max", 10))
            
        with open(self.config_path, "w") as f:
            yaml.safe_dump(self.raw_data, f, sort_keys=False)
        
        # We need to tell the state manager about this update so it reflects live
        from state.event_queue import state_manager
        state_manager.update_capacity("main_floor", capacity, capacity_sitting, capacity_standing)
        return True

    def _save(self):
        with open(self.config_path, "w") as f:
            yaml.safe_dump(self.raw_data, f, sort_keys=False)

def get_config(config_path: str = "config/site_config.yaml"):
    loader = ConfigLoader(config_path)
    return loader.load_and_validate()
