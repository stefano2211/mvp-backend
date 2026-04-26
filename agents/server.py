"""
Industrial Optimus Agents — FastAPI Server
==========================================
Exposes the LangChain Deep Agents orchestrator as an HTTP service
so the API bridge can trigger it and retrieve results.
"""
import base64
import io
import json
import os
import time
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
from pydantic import BaseModel

from .orchestrator import run_pipeline, run_step

app = FastAPI(
    title="Industrial Optimus Agents",
    description="LangChain Deep Agents — System-1 / System-2 core",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SHARED_PATH = Path(os.getenv("SHARED_DATA_PATH", "/app/shared"))
SHARED_PATH.mkdir(parents=True, exist_ok=True)


# ─── Models ──────────────────────────────────────────────────────────────────

class RunRequest(BaseModel):
    """Legacy single-shot request."""
    alert: dict
    screenshot_b64: Optional[str] = None
    dev_mode: bool = False


class StepRequest(BaseModel):
    """Step-by-step screenshot loop request."""
    alert: dict
    screenshot_b64: Optional[str] = None
    action_history: list = []
    step_number: int = 0


# ─── Shared helper ───────────────────────────────────────────────────────────

def _persist_screenshot(screenshot_b64: str) -> None:
    """Save screenshot and metadata to shared volume."""
    screenshot_path = SHARED_PATH / "latest_screenshot.b64"
    with open(screenshot_path, "w") as f:
        f.write(screenshot_b64)

    width, height = "unknown", "unknown"
    try:
        img_bytes = base64.b64decode(screenshot_b64)
        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size
    except Exception as e:
        print(f"Failed to read image dimensions: {e}")

    meta_path = SHARED_PATH / "screenshot_meta.json"
    with open(meta_path, "w") as f:
        json.dump({
            "timestamp": time.time(),
            "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "width": width,
            "height": height,
        }, f)


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "optimus_agents", "version": "2.0.0"}


@app.post("/analyze_step")
async def analyze_step(req: StepRequest):
    """
    PRIMARY endpoint: Execute ONE step of the screenshot loop.
    Called by optimus_api on each loop iteration.
    Returns screen analysis, System-1, System-2, prompts, and the next single action.
    """
    if req.screenshot_b64:
        _persist_screenshot(req.screenshot_b64)

    result = await run_step(
        alert=req.alert,
        screenshot_b64=req.screenshot_b64,
        action_history=req.action_history,
        step_number=req.step_number,
    )
    return result


@app.post("/run")
async def run_agents(req: RunRequest):
    """
    Legacy endpoint: single-shot pipeline (kept for backwards compatibility).
    Prefer /analyze_step for the real screenshot loop.
    """
    if req.screenshot_b64:
        _persist_screenshot(req.screenshot_b64)

    result = await run_pipeline(
        alert=req.alert,
        screenshot_b64=req.screenshot_b64,
    )
    return result
