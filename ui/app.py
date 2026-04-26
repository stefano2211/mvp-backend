"""
Industrial Digital Optimus — Gradio Dashboard v2
=================================================
Replicates Emilio's demo UI with 6 intermediate result boxes,
a real Dev Mode Continue button, and live screenshot display.
"""
import base64
import io
import json
import os
import time

import gradio as gr
import httpx
from PIL import Image

API_URL = os.getenv("API_SERVICE_URL", "http://optimus_api:8000")


# ─── API Helpers ─────────────────────────────────────────────────────────────

def api_get(path: str) -> dict:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.get(f"{API_URL}{path}")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


def api_post(path: str, data: dict) -> dict:
    try:
        with httpx.Client(timeout=10.0) as client:
            r = client.post(f"{API_URL}{path}", json=data)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"error": str(e)}


def get_alert_choices() -> list[tuple[str, str]]:
    result = api_get("/alerts")
    if isinstance(result, list):
        return [(a["label"], a["id"]) for a in result]
    return [
        ("🌡️ Alta Temperatura — Bomba #3", "alta_temperatura_bomba3"),
        ("⚡ Vibración Anómala — Motor A2", "vibracion_anomala_motor"),
        ("🔴 Presión Crítica — Tubería P-07", "presion_critica_tuberia"),
        ("📡 Falla de Comunicación — PLC-Sector C", "falla_comunicacion_plc"),
        ("💧 Nivel Bajo — Tanque T-01", "nivel_bajo_tanque"),
        ("📧 Send test Gmail from Digital Optimus", "send_gmail_test"),
    ]


def b64_to_pil(b64_str: str | None) -> Image.Image | None:
    if not b64_str:
        return None
    try:
        img_bytes = base64.b64decode(b64_str)
        return Image.open(io.BytesIO(img_bytes))
    except Exception:
        return None


def format_logs(logs: list[dict]) -> str:
    lines = []
    for entry in logs:
        icon = {"INFO": "ℹ️", "ERROR": "❌", "DEBUG": "🔍", "WARN": "⚠️"}.get(entry.get("level", "INFO"), "•")
        lines.append(f"[{entry.get('ts', '')}] {icon} [{entry.get('source', '')}] {entry.get('message', '')}")
    return "\n".join(lines) if lines else "— No logs yet —"


def safe_str(val) -> str:
    if val is None:
        return "— Waiting —"
    if isinstance(val, (dict, list)):
        return json.dumps(val, indent=2, ensure_ascii=False)
    return str(val)


# ─── Gradio Actions ──────────────────────────────────────────────────────────

def trigger_alert(alert_id: str, dev_mode: bool):
    if not alert_id:
        return ("⚠️ Please select an alert first.",) + (gr.update(),) * 8

    result = api_post("/trigger-alert", {"alert_id": alert_id, "dev_mode": dev_mode})
    if "error" in result:
        return (f"❌ Error: {result['error']}",) + (gr.update(),) * 8

    alert_info = result.get("alert", {})
    status_text = (
        f"🚀 Pipeline started for: {alert_info.get('label', alert_id)}\n"
        f"Sensor: {alert_info.get('sensor')} = {alert_info.get('value')} {alert_info.get('unit')}\n"
        f"Severity: {alert_info.get('severity')} | Location: {alert_info.get('location')}\n"
        f"Task: {alert_info.get('task')}"
    )
    return (status_text,) + (gr.update(),) * 8


def refresh_dashboard():
    status = api_get("/status")
    logs_data = api_get("/logs?n=80")
    screenshot_data = api_get("/screenshot")

    cycle_status = status.get("cycle_status", "idle")
    loop_step = status.get("loop_step", 0)

    status_icons = {
        "idle": "💤", "starting": "🔄", "analyzing": "🧠",
        "paused": "⏸️", "executing": "⚡", "done": "✅", "error": "❌",
    }
    icon = status_icons.get(cycle_status, "•")

    status_str = (
        f"{icon} **{cycle_status.upper()}** | "
        f"Step: {loop_step} | "
        f"Actions queued: {status.get('actions_remaining', 0)}"
    )

    # Paused banner for dev mode
    if cycle_status == "paused":
        status_str += "\n\n🔧 **DEV_MODE PAUSED** — Check all boxes and click ▶️ Continue when ready."

    logs_text = format_logs(logs_data.get("logs", []))
    screen_analysis = safe_str(status.get("screen_analysis_text"))
    vlm_prompt = safe_str(status.get("vlm_prompt"))
    system1 = safe_str(status.get("system1_text"))
    system2 = safe_str(status.get("system2_text"))
    llm_prompt = safe_str(status.get("llm_prompt"))

    screenshot_img = b64_to_pil(screenshot_data.get("screenshot_b64"))
    if screenshot_img is None:
        screenshot_img = Image.new("RGB", (640, 360), color=(15, 20, 40))

    return status_str, logs_text, screen_analysis, vlm_prompt, system1, system2, llm_prompt, screenshot_img


def dev_mode_continue():
    result = api_post("/dev-continue", {})
    return f"▶️ Continue signal sent: {result.get('status', 'unknown')}"


# ─── Build the Gradio UI ─────────────────────────────────────────────────────

ALERT_CHOICES = get_alert_choices()

with gr.Blocks(
    title="🏭 Industrial Digital Optimus",
    theme=gr.themes.Base(
        primary_hue="orange",
        secondary_hue="slate",
        neutral_hue="slate",
        font=gr.themes.GoogleFont("Inter"),
    ),
    css="""
    footer { display: none !important; }
    .status-bar { font-size: 1.05em; padding: 10px 14px; border-radius: 8px; background: #0f172a; border: 1px solid #334155; }
    .section-label { font-weight: 700; color: #f97316; margin-bottom: 4px; }
    """,
) as demo:

    # ── Header ──────────────────────────────────────────────────────────────
    gr.HTML("""
    <div style="background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
                padding: 20px 28px; border-radius: 12px; margin-bottom: 12px;
                border: 1px solid #334155;">
        <div style="display:flex; align-items:center; gap:14px;">
            <span style="font-size:2.2em;">🏭</span>
            <div>
                <div style="font-size:1.5em; font-weight:800; color:#f97316;">
                    Industrial Digital Optimus
                </div>
                <div style="color:#94a3b8; font-size:0.85em; margin-top:2px;">
                    Sensor → System-1 → System-2 → VLM → Executor (Screenshot Loop)
                </div>
            </div>
        </div>
    </div>
    """)

    # ── Controls ─────────────────────────────────────────────────────────────
    with gr.Row():
        with gr.Column(scale=3):
            alert_dropdown = gr.Dropdown(
                choices=ALERT_CHOICES,
                label="🔔 Select Alert",
                value=ALERT_CHOICES[0][1] if ALERT_CHOICES else None,
                interactive=True,
            )
        with gr.Column(scale=1):
            dev_mode_check = gr.Checkbox(
                label="🔧 Development Mode",
                info="Pause after each VLM + planner step",
                value=False,
            )
        with gr.Column(scale=1):
            trigger_btn = gr.Button("🚀 Trigger Alert", variant="primary", size="lg")
        with gr.Column(scale=1):
            refresh_btn = gr.Button("🔄 Refresh", variant="secondary", size="lg")

    # ── Alert Status Banner ───────────────────────────────────────────────────
    alert_status = gr.Textbox(
        label="📡 Alert Status",
        value="— Select an alert and press Trigger Alert —",
        lines=3,
        interactive=False,
    )

    # ── Pipeline Status Bar ───────────────────────────────────────────────────
    status_md = gr.Markdown("💤 **IDLE** | Step: 0", elem_classes=["status-bar"])

    # ── Main layout: Screenshot LEFT, Results RIGHT ───────────────────────────
    with gr.Row():
        # Live Screenshot
        with gr.Column(scale=2):
            gr.Markdown("### 🖥️ Live Screen")
            screenshot_img = gr.Image(
                label="Windows Host Screen",
                value=Image.new("RGB", (640, 360), color=(15, 20, 40)),
                interactive=False,
                height=360,
            )

        # 📋 Full Log
        with gr.Column(scale=3):
            gr.Markdown("### 📋 Full Log")
            log_box = gr.Textbox(
                label="System Log",
                value="— No activity yet —",
                lines=14,
                max_lines=18,
                interactive=False,
                autoscroll=True,
            )

    # ── 6 Result Boxes (matches Emilio's layout) ──────────────────────────────
    gr.Markdown("### 📊 Step-by-Step Analysis Results")

    with gr.Row():
        with gr.Column():
            gr.Markdown("👁 **Screen Analysis** (VLM)")
            screen_analysis_box = gr.Textbox(
                label="Screen Analysis",
                value="— Waiting —",
                lines=5,
                interactive=False,
            )
        with gr.Column():
            gr.Markdown("🔍 **VLM Prompt** (sent to vision model)")
            vlm_prompt_box = gr.Textbox(
                label="VLM Prompt",
                value="— Waiting —",
                lines=5,
                interactive=False,
            )

    with gr.Row():
        with gr.Column():
            gr.Markdown("⚡ **System-1** (Fast intuition)")
            system1_box = gr.Textbox(
                label="System-1",
                value="— Waiting —",
                lines=5,
                interactive=False,
            )
        with gr.Column():
            gr.Markdown("🧠 **System-2** (Deep reasoning)")
            system2_box = gr.Textbox(
                label="System-2",
                value="— Waiting —",
                lines=5,
                interactive=False,
            )

    with gr.Row():
        with gr.Column():
            gr.Markdown("📡 **LLM Prompt** (to planner)")
            llm_prompt_box = gr.Textbox(
                label="LLM Prompt",
                value="— Waiting —",
                lines=4,
                interactive=False,
            )
        with gr.Column():
            gr.Markdown("✅ **Continue Execution** (Dev Mode)")
            dev_continue_btn = gr.Button("▶️ Continue Execution (only in DEV_MODE)", variant="stop", size="lg")
            dev_status = gr.Textbox(label="Dev Mode Status", value="", interactive=False, lines=2)

    gr.Markdown(
        "<div style='text-align:center; color:#64748b; font-size:0.8em; margin-top:8px;'>"
        "Dashboard auto-refreshes every 3 seconds. "
        "In Dev Mode, the system pauses after each VLM + planner step."
        "</div>"
    )

    # ─── Event Handlers ──────────────────────────────────────────────────────

    all_result_outputs = [
        status_md, log_box,
        screen_analysis_box, vlm_prompt_box,
        system1_box, system2_box,
        llm_prompt_box, screenshot_img,
    ]

    trigger_btn.click(
        fn=trigger_alert,
        inputs=[alert_dropdown, dev_mode_check],
        outputs=[alert_status] + all_result_outputs,
    )

    refresh_btn.click(
        fn=refresh_dashboard,
        outputs=all_result_outputs,
    )

    dev_continue_btn.click(
        fn=dev_mode_continue,
        outputs=[dev_status],
    )

    # Auto-refresh every 3 seconds
    demo.load(
        fn=refresh_dashboard,
        outputs=all_result_outputs,
        every=3,
    )


if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=int(os.getenv("GRADIO_PORT", "7860")),
        show_error=True,
    )
