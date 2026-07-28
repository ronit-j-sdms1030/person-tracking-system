import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from state.event_queue import state_manager

router = APIRouter()

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop = None # Will be set on first connect

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        if self.loop is None:
            self.loop = asyncio.get_running_loop()

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in list(self.active_connections):
            try:
                await connection.send_text(message)
            except Exception:
                self.disconnect(connection)

    def trigger_broadcast(self, zone_id: str):
        if not self.active_connections or self.loop is None:
            return
            
        # Send full status dictionary diff for the zone
        status = state_manager.get_zone_status(zone_id)
        if status:
            msg = json.dumps({"type": "zone_update", "data": status})
            asyncio.run_coroutine_threadsafe(self.broadcast(msg), self.loop)

manager = ConnectionManager()

# Register the callback with state_manager
state_manager.register_callback(manager.trigger_broadcast)

@router.websocket("/live")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send initial state
        await websocket.send_text(json.dumps({
            "type": "initial_state",
            "data": state_manager.get_all_zones_status()
        }))
        
        while True:
            # We don't expect client messages, but we need to keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
