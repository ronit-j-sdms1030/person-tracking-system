#!/bin/bash
# Hard-kills the Uvicorn server immediately without waiting for connections to drain.
echo "Stopping Stark Vision server..."
pkill -f "uvicorn api.main:app" 2>/dev/null
sleep 0.5
# Second pass in case any child processes are still alive
pkill -9 -f "uvicorn api.main:app" 2>/dev/null
pkill -9 -f "api.main:app" 2>/dev/null
echo "Server stopped."
