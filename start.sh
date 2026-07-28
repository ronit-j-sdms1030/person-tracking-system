#!/bin/bash
# Starts the Stark Vision server.
# Usage: ./start.sh
cd "$(dirname "$0")"
source venv/bin/activate
echo "Starting Stark Vision server at http://localhost:8000"
python3 -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload --no-access-log --timeout-graceful-shutdown 1
