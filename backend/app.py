from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import json
import os
from typing import List

app = FastAPI(title="JARVIS Backend")

# Allow CORS for local UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EVENTS_LOG_PATH = "events.log"

# Serve Static UI
app.mount("/ui", StaticFiles(directory="backend/static", html=True), name="static")


EVENTS_LOG_PATH = "events.log"

@app.get("/status")
def get_status():
    return {"status": "active", "system": "JARVIS_PAPER_TRADING"}

@app.get("/events")
def get_events(limit: int = 50):
    """
    Returns the last N events.
    """
    if not os.path.exists(EVENTS_LOG_PATH):
        return []
        
    events = []
    try:
        # Read from end of file efficiently? 
        # For MVP, reading all lines is fine if log isn't huge yet.
        with open(EVENTS_LOG_PATH, "r") as f:
            lines = f.readlines()
            for line in reversed(lines):
                if line.strip():
                    try:
                        events.append(json.loads(line))
                    except:
                        continue
                if len(events) >= limit:
                    break
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return events

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
