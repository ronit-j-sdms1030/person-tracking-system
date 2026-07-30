import os
import signal

# Monkeypatch signal.signal to intercept Uvicorn's shutdown handlers
# This ensures we set vision_runner.running = False immediately on Ctrl+C,
# breaking the StreamingResponse deadlock where Uvicorn waits forever.
_original_signal = signal.signal
def _patched_signal(signum, handler):
    if signum in (signal.SIGINT, signal.SIGTERM):
        def _wrapper(*args, **kwargs):
            global vision_runner
            if vision_runner:
                vision_runner.running = False
            return handler(*args, **kwargs)
        return _original_signal(signum, _wrapper)
    return _original_signal(signum, handler)
signal.signal = _patched_signal

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi import Request, Form

from state.event_queue import state_manager
from api.routes import router as api_router
from api.websocket import router as ws_router
from core.main_vision import VisionRunner

vision_runner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup - Ensure site_config.yaml exists with default sample camera feeds
    config_file = "config/site_config.yaml"
    os.makedirs("config", exist_ok=True)
    if not os.path.exists(config_file) or os.path.getsize(config_file) == 0:
        sample_office = "data/sample_videos/VIDEO-2026-07-28-15-36-24.mp4"
        sample_bus = "data/sample_videos/CCTV_footage_school_bus_students_202607281532.mp4"
        office_src = sample_office if os.path.exists(sample_office) else "data/sample_videos/VIDEO-2026-07-28-15-36-24 (1).mp4"
        bus_src = sample_bus if os.path.exists(sample_bus) else "data/sample_videos/test.mp4"

        baseline_yaml = f"""site_id: stark_demo_site
zones:
- zone_id: main_floor
  capacity_max: 25
  capacity_sitting_max: 15
  capacity_standing_max: 10
  cameras:
  - camera_id: cam_door_1
    adapter: file
    source: {office_src}
    role: both
    frame_skip: 1
    cooldown_seconds: 2.0
  - camera_id: cam_room_1
    adapter: file
    source: {bus_src}
    role: posture
    frame_skip: 1
"""
        with open(config_file, "w") as f:
            f.write(baseline_yaml)

    state_manager.start()
    
    # Start the actual Vision Pipeline!
    global vision_runner
    vision_runner = VisionRunner(config_file, state_manager.event_queue)
    vision_runner.start()
    print("State manager and Vision Pipeline started.")
    
    yield
    
    # Shutdown
    if vision_runner:
        vision_runner.stop()
    state_manager.stop()
    print("State manager and Vision Pipeline stopped.")


app = FastAPI(title="People Counting API", lifespan=lifespan)

# Include routers
app.include_router(api_router)
app.include_router(ws_router)

# Mount static files for dashboard
os.makedirs("dashboard/static", exist_ok=True)
app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")

import uuid
SERVER_SESSION_SECRET = str(uuid.uuid4())

@app.get("/")
def serve_dashboard(request: Request):
    if request.cookies.get("session") != SERVER_SESSION_SECRET:
        return RedirectResponse("/login")
    return FileResponse("dashboard/index.html")

@app.get("/login")
def serve_login():
    return FileResponse("dashboard/login.html")

@app.post("/login")
def login(response: Response, username: str = Form(...), password: str = Form(...)):
    if username == "admin" and password == "password":
        response = Response(status_code=200)
        response.set_cookie(key="session", value=SERVER_SESSION_SECRET, httponly=True)
        return response
    return Response(status_code=401)

@app.get("/logout")
def logout(response: Response):
    response = RedirectResponse("/login")
    response.delete_cookie("session")
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
