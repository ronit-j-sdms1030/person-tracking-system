import threading
import queue
import json
import os
import time
from .config_loader import get_config
from .zone_state import ZoneState

class StateManager:
    def __init__(self):
        self.config = get_config()
        self.zones = {}
        self.camera_to_zone = {}
        
        # Initialize zones and camera mappings
        for zone_cfg in self.config.get("zones", []):
            zone_id = zone_cfg["zone_id"]
            self.zones[zone_id] = ZoneState(zone_cfg)
            for cam in zone_cfg.get("cameras", []):
                self.camera_to_zone[cam["camera_id"]] = zone_id
                
        self.camera_last_event = {} # camera_id -> timestamp
        self.event_queue = queue.Queue()
        self.running = False
        self.consumer_thread = None
        self.callbacks = []
        
        # Setup logging
        os.makedirs("logs", exist_ok=True)
        self.log_file = open("logs/events.jsonl", "a")

    def register_callback(self, callback):
        self.callbacks.append(callback)

    def put_event(self, event: dict):
        self.event_queue.put(event)

    def start(self):
        if not self.running:
            self.running = True
            self.consumer_thread = threading.Thread(target=self._consume_loop, daemon=True)
            self.consumer_thread.start()

    def stop(self):
        self.running = False
        if self.consumer_thread:
            self.event_queue.put(None) # Sentinel to wake up blocking get
            self.consumer_thread.join()
        if self.log_file:
            self.log_file.close()

    def get_all_zones_status(self):
        return {zone_id: state.to_dict() for zone_id, state in self.zones.items()}

    def get_zone_status(self, zone_id: str):
        if zone_id in self.zones:
            return self.zones[zone_id].to_dict()
        return None

    def get_cameras_status(self):
        current_time = time.time()
        cams = []
        for cam_id, zone_id in self.camera_to_zone.items():
            last_event_ts = self.camera_last_event.get(cam_id)
            is_stale = True
            if last_event_ts and (current_time - last_event_ts) <= 30.0:
                is_stale = False
                
            cams.append({
                "camera_id": cam_id,
                "zone_id": zone_id,
                "last_event_timestamp": last_event_ts,
                "is_stale": is_stale
            })
        return cams

    def _consume_loop(self):
        while self.running:
            try:
                event = self.event_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            if event is None: # Sentinel
                break

            cam_id = event.get("camera_id")
            if cam_id:
                self.camera_last_event[cam_id] = event.get("timestamp", time.time())
                zone_id = self.camera_to_zone.get(cam_id)
                if zone_id:
                    self.zones[zone_id].update_from_event(event)
                    
                    # Log event
                    try:
                        self.log_file.write(json.dumps(event) + "\n")
                        self.log_file.flush()
                    except Exception as e:
                        print(f"Error logging event: {e}")

                    # Trigger callbacks
                    for cb in self.callbacks:
                        try:
                            cb(zone_id)
                        except Exception as e:
                            print(f"Callback error: {e}")

            self.event_queue.task_done()

# Global singleton
state_manager = StateManager()
