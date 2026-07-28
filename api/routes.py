from fastapi import APIRouter, HTTPException, UploadFile, Form
from fastapi.responses import JSONResponse
from typing import List, Optional
import os
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
            cam_id = (camera_ids[i] if camera_ids and i < len(camera_ids)
                      else f"cam_upload_{i+1}")
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

        return {"status": "ok", "cameras_added": added}

    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
