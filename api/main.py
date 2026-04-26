"""
Industrial Digital Optimus — FastAPI Bridge
==========================================
The public-facing HTTP bridge between:
  - Windows host client (sends screenshots, receives actions)
  - LangChain Deep Agents service (receives alert triggers, step-by-step analysis)
  - Gradio UI (reads state, logs, and screenshots for display)

v2: Implements the real screenshot loop — one action per step.
"""
import asyncio
import base64
import io
import json
import os
import time
from collections import deque
from typing import Any, Optional

import httpx
from fastapi import FastAPI, File, UploadFile, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ─── App Setup ───────────────────────────────────────────────────────────────
app = FastAPI(
    title="Industrial Optimus API",
    description="Bridge between Windows client, AI agents, and Gradio UI",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

AGENTS_URL = os.getenv("AGENTS_SERVICE_URL", "http://optimus_agents:8001")
MAX_LOOP_STEPS = int(os.getenv("MAX_LOOP_STEPS", "20"))

# ─── In-Memory Shared State ──────────────────────────────────────────────────
state: dict[str, Any] = {
    # Screenshot state
    "latest_screenshot_b64": None,
    "latest_screenshot_ts": None,
    # Alert state
    "current_alert": None,
    # Loop state
    "cycle_status": "idle",       # idle | analyzing | paused | executing | done | error
    "loop_step": 0,               # Current step number in the screenshot loop
    "dev_mode": False,
    "dev_mode_continue": asyncio.Event(),
    # Per-step intermediate results (shown in UI)
    "screen_analysis_text": None,  # VLM screen description
    "system1_text": None,          # System-1 fast scan result
    "system2_text": None,          # System-2 full reasoning
    "vlm_prompt": None,            # The prompt sent to the VLM
    "llm_prompt": None,            # The prompt sent to the LLM planner
    # Action state
    "action_queue": deque(maxlen=10),
    "action_history": [],          # History of all actions executed this cycle
    "next_action": None,           # The most recently planned action (for UI)
}
# Rolling log buffer (last 200 entries)
log_buffer: deque = deque(maxlen=200)


def add_log(level: str, source: str, message: str) -> None:
    """Append a structured log entry to the rolling buffer."""
    entry = {
        "ts": time.strftime("%H:%M:%S"),
        "level": level,
        "source": source,
        "message": message,
    }
    log_buffer.append(entry)
    print(f"[{entry['ts']}][{level}][{source}] {message}")


# ─── Predefined Industrial Alerts ────────────────────────────────────────────
INDUSTRIAL_ALERTS: dict[str, dict] = {
    "alta_temperatura_bomba3": {
        "id": "alta_temperatura_bomba3",
        "label": "🌡️ Alta Temperatura — Bomba #3",
        "sensor": "TEMP-003",
        "value": 98.4,
        "unit": "°C",
        "threshold": 85.0,
        "location": "Sala de Bombas - Sector B",
        "severity": "CRITICAL",
        "task": "Abrir SCADA → Navegar a Bomba #3 → Reducir setpoint a 70°C → Notificar mantenimiento por email",
    },
    "vibracion_anomala_motor": {
        "id": "vibracion_anomala_motor",
        "label": "⚡ Vibración Anómala — Motor A2",
        "sensor": "VIB-A2",
        "value": 15.8,
        "unit": "mm/s",
        "threshold": 7.1,
        "location": "Línea de Producción A",
        "severity": "HIGH",
        "task": "Abrir registro de mantenimiento → Crear ticket → Programar inspección de drone",
    },
    "presion_critica_tuberia": {
        "id": "presion_critica_tuberia",
        "label": "🔴 Presión Crítica — Tubería P-07",
        "sensor": "PRES-P07",
        "value": 142.3,
        "unit": "PSI",
        "threshold": 120.0,
        "location": "Sector C - Planta Principal",
        "severity": "CRITICAL",
        "task": "Activar válvula de alivio → Reducir caudal de entrada → Registrar incidente en sistema ERP",
    },
    "falla_comunicacion_plc": {
        "id": "falla_comunicacion_plc",
        "label": "📡 Falla de Comunicación — PLC-Sector C",
        "sensor": "COMM-PLC-C",
        "value": 0,
        "unit": "status",
        "threshold": 1,
        "location": "Panel de Control - Sector C",
        "severity": "HIGH",
        "task": "Verificar conexión de red → Reiniciar PLC → Activar modo manual → Notificar a ingeniería",
    },
    "nivel_bajo_tanque": {
        "id": "nivel_bajo_tanque",
        "label": "💧 Nivel Bajo — Tanque T-01",
        "sensor": "LEVEL-T01",
        "value": 12.5,
        "unit": "%",
        "threshold": 20.0,
        "location": "Área de Almacenamiento",
        "severity": "MEDIUM",
        "task": "Abrir válvula de llenado → Programar pedido de reabastecimiento → Actualizar dashboard de inventario",
    },
    "send_gmail_test": {
        "id": "send_gmail_test",
        "label": "📧 Send test Gmail from Digital Optimus",
        "sensor": "EMAIL-SYS",
        "value": 1,
        "unit": "trigger",
        "threshold": 0,
        "location": "Digital Communications",
        "severity": "MEDIUM",
        "task": "Open Chrome browser → Navigate to mail.google.com → Click Compose → Fill recipient, subject and body → Click Send",
    },
}


# ─── Models ──────────────────────────────────────────────────────────────────
class AlertTrigger(BaseModel):
    alert_id: str
    dev_mode: bool = False


class ActionItem(BaseModel):
    action_type: str
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    keys: Optional[list[str]] = None
    seconds: Optional[float] = None
    description: str = ""


# ─── Screenshot Loop ─────────────────────────────────────────────────────────
async def run_agent_pipeline(alert: dict) -> None:
    """
    The real screenshot loop.
    
    Each iteration:
      1. Calls /analyze_step on the agents service with the current screenshot + action history
      2. Stores all intermediate results (screen analysis, System-1, System-2, prompts)
      3. In Dev Mode: pauses and waits for user to click Continue
      4. Queues the single next action for the Windows client
      5. Waits for the action to be consumed + screen to update
      6. Repeats until "done" or max steps
    """
    add_log("INFO", "API", f"🚀 Screenshot loop started for: {alert['label']}")
    action_history: list = []
    state["action_history"] = []
    state["loop_step"] = 0

    async with httpx.AsyncClient(timeout=120.0) as client:
        for step in range(MAX_LOOP_STEPS):
            state["loop_step"] = step + 1
            state["cycle_status"] = "analyzing"
            add_log("INFO", "Loop", f"Step {step + 1}/{MAX_LOOP_STEPS} — Analyzing screen...")

            # Build payload for this step
            payload = {
                "alert": alert,
                "screenshot_b64": state.get("latest_screenshot_b64"),
                "action_history": action_history,
                "step_number": step,
            }

            try:
                response = await client.post(
                    f"{AGENTS_URL}/analyze_step",
                    json=payload,
                )
                response.raise_for_status()
                result = response.json()
            except Exception as e:
                add_log("ERROR", "Loop", f"Step {step + 1} failed: {e}")
                state["cycle_status"] = "error"
                return

            # Store all intermediates for Gradio UI
            state["screen_analysis_text"] = result.get("screen_analysis")
            state["system1_text"] = result.get("system1")
            state["system2_text"] = result.get("system2")
            state["vlm_prompt"] = result.get("vlm_prompt")
            state["llm_prompt"] = result.get("llm_prompt")
            next_action = result.get("next_action", {})
            state["next_action"] = next_action

            add_log("INFO", "System1", f"Quick scan: {str(state['system1_text'])[:120]}")
            add_log("INFO", "System2", f"Reasoning complete. Next action: {next_action.get('description', '?')}")

            # ── Dev Mode Pause ────────────────────────────────────────────────
            if state["dev_mode"]:
                state["cycle_status"] = "paused"
                add_log("INFO", "DevMode", f"⏸ DEV_MODE PAUSED after Step {step + 1} — Click Continue in UI to execute plan")
                state["dev_mode_continue"].clear()
                await state["dev_mode_continue"].wait()
                add_log("INFO", "DevMode", "▶️ Resuming execution...")

            # ── Check Termination ─────────────────────────────────────────────
            if not next_action or next_action.get("action_type") == "done":
                state["cycle_status"] = "done"
                add_log("INFO", "Loop", f"✅ Loop complete after {step + 1} steps.")
                return

            # ── Enqueue Single Action ─────────────────────────────────────────
            state["cycle_status"] = "executing"
            state["action_queue"].append(next_action)
            action_history.append({
                "step": step + 1,
                "action": next_action,
            })
            state["action_history"] = action_history

            # ── Wait for Windows Client to Consume the Action ─────────────────
            wait_start = time.time()
            while state["action_queue"]:
                if time.time() - wait_start > 30:
                    add_log("WARN", "Loop", "Timeout waiting for Windows client to consume action")
                    break
                await asyncio.sleep(0.5)

            # Wait for the screen to visually update before next screenshot
            screen_settle_time = float(os.getenv("SCREEN_SETTLE_SECONDS", "2.0"))
            add_log("DEBUG", "Loop", f"Waiting {screen_settle_time}s for screen to settle...")
            await asyncio.sleep(screen_settle_time)

    # If we exit the loop without "done"
    add_log("WARN", "Loop", f"Max steps ({MAX_LOOP_STEPS}) reached without completion.")
    state["cycle_status"] = "done"


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {"status": "ok", "service": "optimus_api", "version": "2.0.0"}


@app.get("/alerts")
def list_alerts():
    """Returns the list of predefined industrial alerts for the UI dropdown."""
    return list(INDUSTRIAL_ALERTS.values())


@app.post("/trigger-alert")
async def trigger_alert(payload: AlertTrigger, background_tasks: BackgroundTasks):
    """
    Trigger the full screenshot loop for a given alert.
    Called by the Gradio UI when the user clicks 'Trigger Alert'.
    """
    alert = INDUSTRIAL_ALERTS.get(payload.alert_id)
    if not alert:
        return JSONResponse(status_code=404, content={"error": f"Alert '{payload.alert_id}' not found."})

    # Reset all state for new cycle
    state["current_alert"] = alert
    state["dev_mode"] = payload.dev_mode
    state["screen_analysis_text"] = None
    state["system1_text"] = None
    state["system2_text"] = None
    state["vlm_prompt"] = None
    state["llm_prompt"] = None
    state["next_action"] = None
    state["action_history"] = []
    state["loop_step"] = 0
    state["action_queue"].clear()
    state["cycle_status"] = "starting"

    add_log("INFO", "UI", f"Alert triggered: {alert['label']} (dev_mode={payload.dev_mode})")
    background_tasks.add_task(run_agent_pipeline, alert)

    return {"status": "pipeline_started", "alert": alert}


@app.post("/screenshot")
async def receive_screenshot(file: UploadFile = File(...)):
    """Receives a screenshot from the Windows client and stores it as base64."""
    contents = await file.read()
    b64 = base64.b64encode(contents).decode("utf-8")
    state["latest_screenshot_b64"] = b64
    state["latest_screenshot_ts"] = time.time()
    add_log("DEBUG", "Client", "Screenshot received and stored.")
    return {"status": "ok", "size_bytes": len(contents)}


@app.get("/screenshot")
def get_screenshot():
    """Returns the latest screenshot as base64 for the Gradio UI."""
    return {
        "screenshot_b64": state.get("latest_screenshot_b64"),
        "timestamp": state.get("latest_screenshot_ts"),
    }


@app.get("/action")
def get_next_action():
    """
    Called by the Windows client to get the next action to execute.
    Returns the next action from the queue, or appropriate status.
    """
    if state["action_queue"]:
        action = state["action_queue"].popleft()
        add_log("INFO", "Executor", f"Dispatching action: {action.get('description', action.get('action_type'))}")
        return action
    elif state["cycle_status"] == "executing":
        # Queue is empty but we were executing → all actions consumed, transition to done
        state["cycle_status"] = "done"
        return {"action_type": "done", "description": "Cycle complete"}
    elif state["cycle_status"] in ("done", "idle", "error"):
        return {"action_type": "done", "description": "Cycle complete"}
    else:
        return {"action_type": "wait", "seconds": 1.0, "description": "Waiting for agent plan"}


@app.post("/dev-continue")
def dev_mode_continue():
    """Signal to continue execution in Development Mode."""
    state["dev_mode_continue"].set()
    add_log("INFO", "DevMode", "▶️ User pressed Continue — resuming loop.")
    return {"status": "continuing"}


@app.get("/status")
def get_status():
    """Full system status snapshot for the Gradio dashboard."""
    return {
        "cycle_status": state["cycle_status"],
        "dev_mode": state["dev_mode"],
        "loop_step": state["loop_step"],
        "current_alert": state["current_alert"],
        # Per-step intermediates
        "screen_analysis_text": state["screen_analysis_text"],
        "system1_text": state["system1_text"],
        "system2_text": state["system2_text"],
        "vlm_prompt": state["vlm_prompt"],
        "llm_prompt": state["llm_prompt"],
        "next_action": state["next_action"],
        # Queue / history
        "actions_remaining": len(state["action_queue"]),
        "action_history": state["action_history"],
        "has_screenshot": state["latest_screenshot_b64"] is not None,
    }


@app.get("/logs")
def get_logs(n: int = 100):
    """Returns the last N log entries."""
    entries = list(log_buffer)[-n:]
    return {"logs": entries}
