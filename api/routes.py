from fastapi import APIRouter, HTTPException, UploadFile, Form
from typing import List
import os
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
    roles: List[str] = Form(...),        # one role per file, same order
    camera_ids: List[str] = Form(None),  # optional; auto-generated if omitted
):
    os.makedirs("data/sample_videos", exist_ok=True)
    added = []

    for i, file in enumerate(files):
        role = roles[i]
        cam_id = camera_ids[i] if camera_ids else f"cam_upload_{i+1}"
        dest = f"data/sample_videos/{file.filename}"

        with open(dest, "wb") as f:
            f.write(await file.read())

        cam = config_loader.add_camera(camera_id=cam_id, source=dest, role=role)
        added.append(cam)

    return {"status": "ok", "cameras_added": added, "note": "restart pipeline to pick up changes"}
