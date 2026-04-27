"""
Windows Client — Screen Capture Loop
======================================
This script runs NATIVELY on Windows (outside Docker).
It continuously captures your screen and sends it to the
Docker-based API, then receives action commands to execute.

Usage:
    pip install -r requirements.txt
    python client.py

Environment:
    OPTIMUS_API_URL — URL of the FastAPI bridge (default: http://localhost:8000)
    SCREENSHOT_INTERVAL_SECONDS — How often to capture the screen (default: 2)
"""
import io
import os
import sys
import time

import mss
import mss.tools
import requests
from PIL import Image
from dotenv import load_dotenv

try:
    from executor import execute_action
except ImportError:
    import importlib.util
    _spec = importlib.util.spec_from_file_location("executor", os.path.join(os.path.dirname(__file__), "executor.py"))
    _executor = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_executor)
    execute_action = _executor.execute_action

load_dotenv()

API_URL = os.getenv("OPTIMUS_API_URL", "http://localhost:8000")
INTERVAL = float(os.getenv("SCREENSHOT_INTERVAL_SECONDS", "2"))

# ─── Screenshot Capture ───────────────────────────────────────────────────────

def capture_screen() -> bytes:
    """Capture the primary monitor and return as JPEG bytes."""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # Monitor 1 = primary screen
        raw = sct.grab(monitor)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        # Downscale to 1280x720 to reduce bandwidth if needed
        img = img.resize((1280, 720), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()


def send_screenshot(img_bytes: bytes) -> bool:
    """Send a screenshot to the API service."""
    try:
        response = requests.post(
            f"{API_URL}/screenshot",
            files={"file": ("screenshot.jpg", img_bytes, "image/jpeg")},
            timeout=5.0,
        )
        return response.ok
    except Exception as e:
        print(f"[WARN] Could not send screenshot: {e}")
        return False


def poll_action() -> dict | None:
    """Ask the API for the next action to execute."""
    try:
        response = requests.get(f"{API_URL}/action", timeout=5.0)
        if response.ok:
            return response.json()
    except Exception as e:
        print(f"[WARN] Could not poll action: {e}")
    return None


def check_api_health() -> bool:
    """Verify the API is reachable before starting the loop."""
    try:
        r = requests.get(f"{API_URL}/health", timeout=3.0)
        return r.ok
    except Exception:
        return False


# ─── Main Loop ────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  🏭 Industrial Digital Optimus — Windows Client")
    print("=" * 60)
    print(f"  API URL: {API_URL}")
    print(f"  Screenshot interval: {INTERVAL}s")
    print()

    # Wait for the API to be ready
    print("  ⏳ Waiting for API service to be ready...")
    attempts = 0
    while not check_api_health():
        attempts += 1
        if attempts > 30:
            print("  ❌ API not reachable after 30 attempts. Is Docker running?")
            sys.exit(1)
        time.sleep(2)
    print("  ✅ API is ready! Starting capture loop...\n")

    last_action_type = "done"
    idle_count = 0

    while True:
        loop_start = time.time()

        # 1. Capture and send screenshot
        img_bytes = capture_screen()
        ok = send_screenshot(img_bytes)
        status_icon = "📸" if ok else "⚠️"
        print(f"  {status_icon} Screenshot sent ({len(img_bytes) // 1024}KB)")

        # 2. Poll for the next action
        action = poll_action()
        if action:
            action_type = action.get("action_type", "wait")
            print(f"  ➡️  Action received: [{action_type.upper()}] {action.get('description', '')}")

            if action_type == "done":
                print("  ✅ Cycle complete — agent has finished all actions.")
                last_action_type = "done"
                idle_count += 1
            elif action_type == "wait":
                wait_s = action.get("seconds", 1.0)
                print(f"  ⏳ Waiting {wait_s}s as instructed by agent...")
                time.sleep(wait_s)
                idle_count += 1
            else:
                # Execute the action on Windows
                execute_action(action)
                last_action_type = action_type
                idle_count = 0
        else:
            print("  💤 No action (agent is idle or thinking...)")
            idle_count += 1

        # 3. Adaptive interval: fast when active, slow when idle between cycles
        effective_interval = INTERVAL if idle_count < 3 else 5.0
        elapsed = time.time() - loop_start
        sleep_time = max(0, effective_interval - elapsed)
        time.sleep(sleep_time)


if __name__ == "__main__":
    main()
