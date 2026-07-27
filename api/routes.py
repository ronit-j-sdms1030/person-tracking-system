from fastapi import APIRouter, HTTPException
from state.event_queue import state_manager

router = APIRouter()

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
