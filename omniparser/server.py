"""
OmniParser V2 API Server
========================
FastAPI wrapper around Microsoft's official OmniParser V2 (YOLOv8 + Florence-2).
Receives a screenshot, returns a Set-of-Marks annotated image plus a list of
interactive UI elements with pixel coordinates.

Contract (kept compatible with the agents/tools/screen_tools.py caller):
  POST /parse   {"image_b64": "<base64 PNG/JPEG>"}
    → {
        "status": "success",
        "annotated_image_b64": "<base64 of SOM-labeled image>",
        "elements": [
            {
              "id": int,
              "type": "text" | "icon",
              "text": str,
              "interactivity": bool,
              "center_x": int, "center_y": int,
              "bbox_ratio": [x1, y1, x2, y2]   # 0..1 relative to image
            },
            ...
        ],
        "processing_time_ms": int
      }
"""
import base64
import io
import os
import sys
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image

# Make the cloned OmniParser repo importable
sys.path.append("/opt/OmniParser")
from util.omniparser import Omniparser  # noqa: E402

app = FastAPI(title="OmniParser API", version="2.0")

# ─── Model Loading ───────────────────────────────────────────────────────────
CONFIG: dict[str, Any] = {
    "som_model_path": os.getenv(
        "OMNIPARSER_SOM_MODEL", "/opt/OmniParser/weights/icon_detect/model.pt"
    ),
    "caption_model_name": "florence2",
    "caption_model_path": os.getenv(
        "OMNIPARSER_CAPTION_MODEL",
        "/opt/OmniParser/weights/icon_caption_florence",
    ),
    "BOX_TRESHOLD": float(os.getenv("OMNIPARSER_BOX_THRESHOLD", "0.05")),
}

print(f"[OmniParser] Loading models with config: {CONFIG}")
omniparser = Omniparser(CONFIG)
print("[OmniParser] Ready.")


# ─── Request / Response Models ───────────────────────────────────────────────
class ParseRequest(BaseModel):
    image_b64: str


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "omniparser", "version": "2.0"}


@app.post("/parse")
async def parse_image(req: ParseRequest):
    """
    Run OmniParser V2 on the given screenshot.
    """
    try:
        start = time.time()

        # Decode once to get pixel dimensions (bbox returned by OmniParser is in ratio form)
        img_bytes = base64.b64decode(req.image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size

        # Run inference (YOLOv8 detection + OCR + Florence-2 captioning)
        dino_labeled_img, parsed_content_list = omniparser.parse(req.image_b64)

        # Normalize the parsed_content_list into our agent-friendly schema
        elements = []
        for idx, item in enumerate(parsed_content_list):
            bbox = item.get("bbox", [0.0, 0.0, 0.0, 0.0])  # ratio coords
            cx = int((bbox[0] + bbox[2]) / 2 * width)
            cy = int((bbox[1] + bbox[3]) / 2 * height)
            elements.append({
                "id": idx,
                "type": item.get("type", "unknown"),
                "text": item.get("content", "") or "",
                "interactivity": bool(item.get("interactivity", True)),
                "center_x": cx,
                "center_y": cy,
                "bbox_ratio": bbox,
                "source": item.get("source", ""),
            })

        latency_ms = int((time.time() - start) * 1000)
        print(f"[OmniParser] Parsed {len(elements)} elements in {latency_ms}ms")

        return {
            "status": "success",
            "annotated_image_b64": dino_labeled_img,
            "elements": elements,
            "image_width": width,
            "image_height": height,
            "processing_time_ms": latency_ms,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"OmniParser failed: {e}")
