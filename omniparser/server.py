import base64
import io
import time
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from PIL import Image

app = FastAPI(title="OmniParser API", version="1.0")

class ParseRequest(BaseModel):
    image_b64: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/parse")
async def parse_image(req: ParseRequest):
    """
    Placeholder for the actual OmniParser inference.
    In a real scenario, this decodes the image, runs YOLOv8 + Florence-2,
    and returns a base64 image with Set-of-Marks drawn, along with the parsed elements.
    """
    try:
        # Decode image to verify it's valid
        img_bytes = base64.b64decode(req.image_b64)
        img = Image.open(io.BytesIO(img_bytes))
        width, height = img.size

        # MOCK IMPLEMENTATION:
        # Here we would run the actual OmniParser models.
        # For now, we return the original image and a mock parsed element.
        
        parsed_elements = [
            {
                "id": 1,
                "type": "text_input",
                "text": "Search",
                "center_x": int(width * 0.5),
                "center_y": int(height * 0.1),
            },
            {
                "id": 2,
                "type": "button",
                "text": "Submit",
                "center_x": int(width * 0.5),
                "center_y": int(height * 0.2),
            }
        ]

        return {
            "status": "success",
            "annotated_image_b64": req.image_b64, # returning original for mock
            "elements": parsed_elements,
            "processing_time_ms": 1500
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
