import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from state.event_queue import state_manager
from api.routes import router as api_router
from api.websocket import router as ws_router
from core.main_vision import VisionRunner

vision_runner = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
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

@app.get("/")
def serve_dashboard():
    return FileResponse("dashboard/index.html")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
