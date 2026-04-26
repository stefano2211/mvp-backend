"""
Screen Tools — tools for accessing and analyzing the Windows host screenshot.
"""
import base64
import json
import os
import time
from pathlib import Path


# Path to the shared volume where the latest screenshot is stored
SHARED_PATH = Path(os.getenv("SHARED_DATA_PATH", "/app/shared"))


from typing import Any

def get_latest_screenshot() -> Any:
    """
    Retrieve the latest screenshot captured from the Windows host operator screen.
    Returns a JSON string with the base64-encoded image and metadata.
    If no screenshot is available, returns a description of an empty desktop.
    """
    screenshot_file = SHARED_PATH / "latest_screenshot.b64"
    metadata_file = SHARED_PATH / "screenshot_meta.json"

    if not screenshot_file.exists():
        return json.dumps({
            "has_screenshot": False,
            "message": "No screenshot available yet. The Windows client has not sent a capture.",
            "image_b64": None,
        })

    with open(screenshot_file, "r") as f:
        b64_data = f.read().strip()

    metadata = {}
    if metadata_file.exists():
        with open(metadata_file, "r") as f:
            metadata = json.load(f)

    # Call OmniParser to get the Set-of-Marks annotated image
    import httpx
    omniparser_url = os.getenv("OMNIPARSER_URL", "http://omniparser_api:8003/parse")
    interactive_elements = []
    try:
        r = httpx.post(omniparser_url, json={"image_b64": b64_data}, timeout=30.0)
        r.raise_for_status()
        parsed_data = r.json()
        if parsed_data.get("status") == "success":
            b64_data = parsed_data.get("annotated_image_b64", b64_data)
            interactive_elements = parsed_data.get("elements", [])
    except Exception as e:
        print(f"Failed to call OmniParser: {e}")

    age_seconds = time.time() - metadata.get("timestamp", 0)

    # Return multimodal LangChain format: text + image_url
    info = {
        "has_screenshot": True,
        "interactive_elements": interactive_elements,
        "width": metadata.get("width", "unknown"),
        "height": metadata.get("height", "unknown"),
        "captured_at": metadata.get("captured_at", "unknown"),
        "age_seconds": round(age_seconds, 1),
        "is_stale": age_seconds > 10,
    }
    
    return [
        {"type": "text", "text": json.dumps(info)},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_data}"}}
    ]


def describe_screen_region(x1: int, y1: int, x2: int, y2: int) -> str:
    """
    Request a description of a specific region of the screen.
    Useful for focusing on specific UI elements like buttons or text fields.
    
    Args:
        x1: Left coordinate of the region
        y1: Top coordinate of the region
        x2: Right coordinate of the region
        y2: Bottom coordinate of the region
    """
    return json.dumps({
        "region": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
        "note": "Region crop analysis: coordinates recorded. Full screenshot analysis covers this region.",
    })
