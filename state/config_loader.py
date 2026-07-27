import yaml
import os

class ConfigLoader:
    def __init__(self, config_path: str = "config/site_config.yaml"):
        self.config_path = config_path
        self.site_id = None
        self.zones = []

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
            if not cameras or not isinstance(cameras, list):
                raise ValueError(f"Zone {zone['zone_id']} missing or invalid 'cameras'.")
                
            for cam in cameras:
                if "camera_id" not in cam:
                    raise ValueError(f"Camera in zone {zone['zone_id']} missing 'camera_id'.")
                if "role" not in cam:
                    raise ValueError(f"Camera {cam['camera_id']} missing 'role'.")
                    
        return data

def get_config(config_path: str = "config/site_config.yaml"):
    loader = ConfigLoader(config_path)
    return loader.load_and_validate()
