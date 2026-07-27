# Contract — Event Schema & Config Schema

## 1. Event format (Person A emits, Person B consumes)

```json
{
  "camera_id": "cam_door_1",
  "timestamp": 1234567890.12,
  "track_id": 17,
  "bbox": [x1, y1, x2, y2],
  "event": "entered" | "exited" | null,
  "posture": "sitting" | "standing" | "unknown" | null
}
```

## 2. Site config schema

```yaml
site_id: office_pune_01
zones:
  - zone_id: main_floor
    capacity_max: 40
    cameras:
      - camera_id: cam_door_1
        adapter: file          # rtsp | file | usb
        source: data/sample_videos/doorway_footage.mp4
        role: entry_exit       # entry_exit | posture | both
        line: {p1: [120, 400], p2: [520, 410]}
        direction_in: down
        cooldown_seconds: 2.0
        cooldown_px: 40
      - camera_id: cam_room_1
        adapter: file
        source: data/sample_videos/interior_footage.mp4
        role: posture
```

## 3. Queue interface

Single-process `queue.Queue()`. Vision pipeline calls `queue.put(event_dict)`.
State layer runs a consumer thread calling `queue.get()` and updating ZoneState.
