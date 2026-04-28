#!/bin/bash
set -e

echo "=========================================="
echo "  🖥️  Digital Optimus — Virtual Desktop"
echo "=========================================="

# 1. Start the virtual display (1280x720, 24-bit color)
echo "[entrypoint] Cleaning up old Xvfb locks..."
rm -f /tmp/.X99-lock
echo "[entrypoint] Starting Xvfb on :99 (1280x720)..."
Xvfb :99 -screen 0 1280x720x24 -ac &
XVFB_PID=$!
sleep 2

# Verify Xvfb is running
if ! kill -0 $XVFB_PID 2>/dev/null; then
    echo "[entrypoint] ERROR: Xvfb failed to start!"
    exit 1
fi
echo "[entrypoint] ✅ Xvfb is running (PID $XVFB_PID)"

# 2. Start a lightweight window manager
echo "[entrypoint] Starting fluxbox window manager..."
fluxbox &
sleep 1
echo "[entrypoint] ✅ Fluxbox is running"

# 3. Start Chromium browser (visible in the virtual desktop)
echo "[entrypoint] Launching Chromium..."
chromium \
    --no-sandbox \
    --disable-gpu \
    --disable-software-rasterizer \
    --disable-dev-shm-usage \
    --window-size=1280,720 \
    --window-position=0,0 \
    --start-maximized \
    "https://www.google.com" &
sleep 3
echo "[entrypoint] ✅ Chromium is running"

# 4. Wait for the API to be ready
echo "[entrypoint] Waiting for API at ${OPTIMUS_API_URL}..."
RETRIES=0
until curl -sf "${OPTIMUS_API_URL}/health" > /dev/null 2>&1; do
    RETRIES=$((RETRIES + 1))
    if [ $RETRIES -gt 60 ]; then
        echo "[entrypoint] ERROR: API not reachable after 60 attempts"
        exit 1
    fi
    sleep 2
done
echo "[entrypoint] ✅ API is ready!"

# 5. Start the client loop
echo "[entrypoint] 🚀 Starting screenshot capture loop..."
exec python client.py
