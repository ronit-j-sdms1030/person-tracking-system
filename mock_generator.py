import time
import random
import threading
from state.event_queue import state_manager

class MockEventGenerator:
    def __init__(self, state_mgr):
        self.state_mgr = state_mgr
        self.running = False
        self.thread = None
        self.track_id_counter = 1

    def generate_random_event(self):
        cams = self.state_mgr.camera_to_zone.keys()
        if not cams:
            return None
            
        cam_id = random.choice(list(cams))
        
        # In our specific test case, cam_door_1 is entry_exit, cam_room_1 is posture
        is_entry = "door" in cam_id
        
        event_dict = {
            "camera_id": cam_id,
            "timestamp": time.time(),
            "track_id": random.randint(1, 100) if not is_entry else self.track_id_counter,
            "bbox": [
                random.randint(0, 100),
                random.randint(0, 100),
                random.randint(100, 200),
                random.randint(100, 200)
            ]
        }
        
        if is_entry:
            event_dict["event"] = random.choice(["entered", "exited"])
            event_dict["posture"] = None
            self.track_id_counter += 1
        else:
            event_dict["event"] = None
            event_dict["posture"] = random.choice(["sitting", "standing", "unknown"])
            
        return event_dict

    def _loop(self):
        while self.running:
            evt = self.generate_random_event()
            if evt:
                self.state_mgr.put_event(evt)
            time.sleep(random.uniform(1.0, 3.0))

    def start(self):
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join()
