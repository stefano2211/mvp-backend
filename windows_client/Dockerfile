FROM python:3.11-slim

# Install virtual display, window manager, browser, and X11 tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    fluxbox \
    x11-utils \
    xdotool \
    scrot \
    chromium \
    fonts-liberation \
    fonts-noto-color-emoji \
    dbus-x11 \
    procps \
    curl \
    python3-tk \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
# python-xlib is needed for pyautogui on Linux
RUN pip install --no-cache-dir -r requirements.txt python-xlib

COPY . .
COPY entrypoint.sh /entrypoint.sh
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh

ENV DISPLAY=:99
ENV OPTIMUS_API_URL=http://optimus_api:8000

CMD ["/entrypoint.sh"]
