import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from state.event_queue import state_manager
from api.routes import router as api_router
from api.websocket import router as ws_router
from mock_generator import MockEventGenerator

# We can start the mock generator if we want to run end-to-end without Person A
mock_gen = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    state_manager.start()
    
    # Start mock generator for testing purposes
    global mock_gen
    mock_gen = MockEventGenerator(state_manager)
    mock_gen.start()
    print("State manager and Mock Event Generator started.")
    
    yield
    
    # Shutdown
    if mock_gen:
        mock_gen.stop()
    state_manager.stop()
    print("State manager stopped.")


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
