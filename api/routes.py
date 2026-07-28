from fastapi import APIRouter, HTTPException, UploadFile, Form
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

@router.get("/cameras")
def get_cameras_status():
    return state_manager.get_cameras_status()

@router.post("/upload-cameras")
async def upload_cameras(
    files: List[UploadFile],
    roles: List[str] = Form(...),
    camera_ids: Optional[List[str]] = Form(None),
):
    try:
        os.makedirs("data/sample_videos", exist_ok=True)
        added = []

        for i, file in enumerate(files):
            role = roles[i] if i < len(roles) else "entry_exit"
            
            # Map the first two uploads to the hardcoded UI slots
            default_ids = ["cam_door_1", "cam_room_1"]
            if camera_ids and i < len(camera_ids) and camera_ids[i]:
                cam_id = camera_ids[i]
            else:
                cam_id = default_ids[i] if i < len(default_ids) else f"cam_upload_{i+1}"
                
            dest = f"data/sample_videos/{file.filename}"

            with open(dest, "wb") as f:
                content = await file.read()
                f.write(content)

            # Add camera to config (saves to site_config.yaml)
            try:
                cam = config_loader.add_camera(camera_id=cam_id, source=dest, role=role)
            except ValueError as e:
                # camera_id already exists — just reuse dest path
                cam = {"camera_id": cam_id, "source": dest, "role": role}

            added.append(cam)

            # Hot-start a new camera thread in the running pipeline
            from api.main import vision_runner
            if vision_runner is not None:
                cam_config = {
                    "camera_id": cam_id,
                    "adapter": "file",
                    "source": dest,
                    "role": role,
                    "cooldown_seconds": 2.0,
                    "frame_skip": 1,
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
            if default_zone and cam_id not in state_manager.camera_to_zone:
                state_manager.camera_to_zone[cam_id] = default_zone

        return {"status": "ok", "cameras_added": added}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@router.get("/video_feed/{camera_id}")
def video_feed(camera_id: str):
    from api.main import vision_runner
    def gen():
        while True:
            if vision_runner and camera_id in vision_runner.latest_frames:
                frame = vision_runner.latest_frames[camera_id]
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
