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
    # Startup - Hard reset site_config.yaml to empty camera list
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

    state_manager.start()
    
    # Start the actual Vision Pipeline!
    global vision_runner
    vision_runner = VisionRunner("config/site_config.yaml", state_manager.event_queue)
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
SESSION_SECRET_FILE = ".session_secret"
if os.path.exists(SESSION_SECRET_FILE):
    try:
        with open(SESSION_SECRET_FILE, "r") as f:
            SERVER_SESSION_SECRET = f.read().strip()
    except Exception:
        SERVER_SESSION_SECRET = str(uuid.uuid4())
else:
    SERVER_SESSION_SECRET = str(uuid.uuid4())
    try:
        with open(SESSION_SECRET_FILE, "w") as f:
            f.write(SERVER_SESSION_SECRET)
    except Exception:
        pass

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
        res = Response(status_code=200)
        res.set_cookie(
            key="session", 
            value=SERVER_SESSION_SECRET, 
            httponly=True,
            max_age=2592000,
            path="/",
            samesite="lax"
        )
        return res
    return Response(status_code=401)

@app.get("/logout")
def logout(response: Response):
    res = RedirectResponse("/login")
    res.delete_cookie("session", path="/")
    return res

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
