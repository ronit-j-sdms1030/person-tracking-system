from fastapi import APIRouter, HTTPException, UploadFile, Form, Request
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List, Optional
import os
import time
import threading
from state.event_queue import state_manager
from state.config_loader import ConfigLoader

router = APIRouter()
config_loader = ConfigLoader()

@router.get("/status")
def get_all_status():
    return state_manager.get_all_zones_status()

@router.get("/status/{zone_id}")
def get_zone_status(zone_id: str):
    status = state_manager.get_zone_status(zone_id)
    if not status:
        raise HTTPException(status_code=404, detail="Zone not found")
    return status

@router.post("/reset")
def reset_data():
    from api.main import vision_runner
    
    # 1. Clear cameras from config/site_config.yaml
    baseline_yaml = """site_id: stark_demo_site
zones:
- zone_id: main_floor
  capacity_max: 25
  capacity_sitting_max: 15
  capacity_standing_max: 10
  cameras: []
"""
    os.makedirs("config", exist_ok=True)
    with open("config/site_config.yaml", "w") as f:
        f.write(baseline_yaml)

    # 2. Stop camera threads & clear frame cache
    if vision_runner:
        adapters = getattr(vision_runner, "adapters", {})
        for cam_id in list(adapters.keys()):
            try:
                vision_runner.stop_camera(cam_id)
            except Exception as e:
                logger.warning(f"Error stopping camera {cam_id}: {e}")
        if hasattr(vision_runner, "latest_frames"):
            vision_runner.latest_frames.clear()
        if hasattr(vision_runner, "adapters"):
            vision_runner.adapters.clear()
        if hasattr(vision_runner, "stopped_cameras"):
            vision_runner.stopped_cameras.clear()

    # 3. Clear state manager camera mapping and zone state
    state_manager.camera_to_zone.clear()
    state_manager.reset_zone("main_floor")
    
    return {"status": "ok", "message": "Hard reset completed successfully"}

@router.get("/cameras")
def get_cameras_status():
    return state_manager.get_cameras_status()

@router.get("/export-csv")
def export_csv_report():
    import csv, io, json
    from fastapi.responses import Response
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Timestamp", "Camera ID", "Event Type", "Track ID", "Zone ID"])
    
    if os.path.exists("logs/events.jsonl"):
        with open("logs/events.jsonl", "r") as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    ts = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(data.get("timestamp", time.time())))
                    writer.writerow([ts, data.get("camera_id", "cam_1"), data.get("event", "count_update"), data.get("track_id", "N/A"), "main_floor"])
                except Exception:
                    pass
    
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=headcount_audit_report.csv"}
    )

@router.post("/capacity")
def set_capacity(
    capacity: Optional[int] = Form(None),
    capacity_sitting: Optional[int] = Form(None),
    capacity_standing: Optional[int] = Form(None),
):
    config_loader.update_capacity(
        capacity=capacity,
        capacity_sitting=capacity_sitting,
        capacity_standing=capacity_standing
    )
    return {"status": "ok", "message": "Capacity updated successfully"}

@router.post("/upload-cameras")
async def upload_cameras(
    files: List[UploadFile],
    roles: List[str] = Form(...),
    slots: Optional[List[str]] = Form(None),
    cam_capacities: Optional[List[int]] = Form(None),
    capacity: Optional[int] = Form(None),
    capacity_sitting: Optional[int] = Form(None),
    capacity_standing: Optional[int] = Form(None),
):
    try:
        os.makedirs("data/sample_videos", exist_ok=True)
        added = []

        if capacity is not None or capacity_sitting is not None or capacity_standing is not None:
            config_loader.update_capacity(capacity=capacity, capacity_sitting=capacity_sitting, capacity_standing=capacity_standing)

        from api.main import vision_runner

        # Determine target camera IDs in this upload batch
        new_cam_ids = []
        for i, file in enumerate(files):
            if slots and i < len(slots):
                new_cam_ids.append(slots[i])
            else:
                new_cam_ids.append("cam_door_1" if i == 0 else ("cam_room_1" if i == 1 else f"cam_upload_{i+1}"))

        # Stop and remove old cameras that are not in the new batch
        removed_ids = config_loader.clear_cameras_except(new_cam_ids)
        if vision_runner:
            for rid in removed_ids:
                vision_runner.stop_camera(rid)

        for i, file in enumerate(files):
            role = roles[i] if i < len(roles) else "entry_exit"
            cam_id = new_cam_ids[i]
            dest = f"data/sample_videos/{file.filename}"

            with open(dest, "wb") as f:
                while chunk := await file.read(1024 * 1024):
                    f.write(chunk)

            # Get per-camera capacity if provided
            cam_cap = cam_capacities[i] if (cam_capacities and i < len(cam_capacities)) else capacity

            # Add camera to config (saves to site_config.yaml)
            cam = config_loader.add_camera(camera_id=cam_id, source=dest, role=role, capacity=cam_cap)
            added.append(cam_id)
            
            # Hot-start a new camera thread in the running pipeline
            if vision_runner is not None:
                vision_runner.stop_camera(cam_id)
                time.sleep(0.3)
                vision_runner.stopped_cameras.discard(cam_id)
                    
                cam_config = {
                    "camera_id": cam_id,
                    "adapter": "file",
                    "source": dest,
                    "role": role,
                    "cooldown_seconds": 2.0,
                    "frame_skip": 3,
                }
                t = threading.Thread(
                    target=vision_runner._run_camera,
                    args=(cam_config,),
                    name=f"cam-{cam_id}",
                    daemon=True,
                )
                vision_runner.threads.append(t)
                t.start()

            # Register camera into the live state_manager so its events update the dashboard
            default_zone = list(state_manager.zones.keys())[0] if state_manager.zones else None
            if default_zone:
                state_manager.camera_to_zone[cam_id] = default_zone

        return {"status": "ok", "cameras_added": added}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.post("/cameras/{camera_id}/capacity")
def set_camera_capacity(camera_id: str, capacity: int = Form(...)):
    config_loader.update_camera_capacity(camera_id, capacity)
    return {"status": "ok", "camera_id": camera_id, "capacity": capacity}

@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str):
    success = config_loader.remove_camera(camera_id)
    # If not found, we just consider it already deleted and continue gracefully.
        
    from api.main import vision_runner
    if vision_runner:
        vision_runner.stop_camera(camera_id)
        
    if camera_id in state_manager.camera_to_zone:
        del state_manager.camera_to_zone[camera_id]
        
    return {"status": "ok", "message": f"Deleted {camera_id}"}

@router.post("/cameras/{camera_id}/pause")
def pause_camera(camera_id: str):
    from api.main import vision_runner
    if vision_runner:
        vision_runner.pause_camera(camera_id)
    return {"status": "ok", "message": f"Paused {camera_id}"}

@router.post("/cameras/{camera_id}/resume")
def resume_camera(camera_id: str):
    from api.main import vision_runner
    if vision_runner:
        vision_runner.resume_camera(camera_id)
    return {"status": "ok", "message": f"Resumed {camera_id}"}

@router.post("/cameras/{camera_id}/seek")
def seek_camera(camera_id: str, percent: float):
    from api.main import vision_runner
    if vision_runner:
        vision_runner.seek_camera(camera_id, percent)
    return {"status": "ok", "message": f"Seeked {camera_id} to {percent}%"}

@router.get("/cameras/{camera_id}/position")
def get_position(camera_id: str):
    from api.main import vision_runner
    if vision_runner and hasattr(vision_runner, 'adapters') and camera_id in vision_runner.adapters:
        return {"percent": vision_runner.adapters[camera_id].get_position()}
    return {"percent": 0.0}

@router.get("/video_feed/{camera_id}")
async def video_feed(camera_id: str, request: Request):
    from api.main import vision_runner
    import asyncio
    async def gen():
        while True:
            if await request.is_disconnected():
                break
            if not vision_runner or not vision_runner.running:
                break
            if camera_id in vision_runner.latest_frames:
                frame = vision_runner.latest_frames[camera_id]
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            await asyncio.sleep(0.05)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
