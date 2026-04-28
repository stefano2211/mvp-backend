FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System dependencies required by OmniParser (OpenCV, EasyOCR, PaddleOCR, git)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    libgl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Clone the official Microsoft OmniParser repo (V2)
RUN git clone --depth 1 https://github.com/microsoft/OmniParser.git /opt/OmniParser

WORKDIR /opt/OmniParser

# Install OmniParser deps. We install torch separately to pick a CUDA build,
# and strip some heavy/unused packages from the default requirements.
RUN pip install --upgrade pip && \
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121 && \
    pip install \
        easyocr \
        supervision==0.18.0 \
        transformers \
        ultralytics==8.3.70 \
        numpy==1.26.4 \
        opencv-python-headless \
        dill \
        accelerate \
        timm \
        einops==0.8.0 \
        paddlepaddle \
        paddleocr \
        huggingface_hub \
        fastapi==0.115.6 \
        "uvicorn[standard]==0.34.0" \
        pydantic==2.10.6 \
        pillow==11.1.0

# Download OmniParser V2 weights from HuggingFace
RUN mkdir -p weights && \
    for f in icon_detect/train_args.yaml icon_detect/model.pt icon_detect/model.yaml \
             icon_caption/config.json icon_caption/generation_config.json icon_caption/model.safetensors; do \
        hf download microsoft/OmniParser-v2.0 "$f" --local-dir weights; \
    done && \
    mv weights/icon_caption weights/icon_caption_florence

# Copy our custom FastAPI wrapper on top
COPY server.py /opt/OmniParser/server.py

EXPOSE 8003

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8003"]
