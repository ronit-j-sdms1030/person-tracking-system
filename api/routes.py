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
            # Map upload to UI slot based on role
            if role == "posture":
                cam_id = "cam_room_1"
            elif role == "entry_exit":
                cam_id = "cam_door_1"
            else:
                cam_id = f"cam_upload_{i+1}"
                
            dest = f"data/sample_videos/{file.filename}"

            with open(dest, "wb") as f:
                content = await file.read()
                f.write(content)

            # Add camera to config (saves to site_config.yaml)
            cam = config_loader.add_camera(camera_id=cam_id, source=dest, role=role)

            added.append(cam)

            # Hot-start a new camera thread in the running pipeline
            from api.main import vision_runner
            if vision_runner is not None:
                # If a thread for this camera is already running, stop it first!
                if cam_id in [c.get("camera_id") for c in vision_runner.cameras_config] or cam_id in vision_runner.latest_frames or any(t.name == f"cam-{cam_id}" and t.is_alive() for t in vision_runner.threads):
                    vision_runner.stop_camera(cam_id)
                    time.sleep(1.0) # give it a moment to release cv2 resources
                    vision_runner.stopped_cameras.discard(cam_id)
                    
                cam_config = {
                    "camera_id": cam_id,
                    "adapter": "file",
                    "source": dest,
                    "role": role,
                    "cooldown_seconds": 2.0,
                    "frame_skip": 3,  # Increased from 1 to reduce YOLO load on 60fps video
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

@router.delete("/cameras/{camera_id}")
def delete_camera(camera_id: str):
    success = config_loader.remove_camera(camera_id)
    if not success:
        raise HTTPException(status_code=404, detail="Camera not found")
        
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
def video_feed(camera_id: str):
    from api.main import vision_runner
    def gen():
        while True:
            if not vision_runner or not vision_runner.running:
                break
            if camera_id in vision_runner.latest_frames:
                frame = vision_runner.latest_frames[camera_id]
                if frame:
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            time.sleep(0.05)
    return StreamingResponse(gen(), media_type="multipart/x-mixed-replace; boundary=frame")
