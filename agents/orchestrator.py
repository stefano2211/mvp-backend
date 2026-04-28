"""
Industrial Optimus Orchestrator
================================
The System-2 "Thinker" — the main LangChain Deep Agent that
coordinates System-1 subagents and produces the final action plan.

Supports two modes:
  - run_step(): Step-by-step screenshot loop (primary mode)
  - run_pipeline(): Legacy single-shot mode (kept for compatibility)

Architecture (v3 — Flat):
  Instead of nesting subagents inside the LangGraph orchestrator
  (which caused infinite recursion loops with the 9B model), we now
  pre-compute subagent results in Python and inject them as context.
  The orchestrator LLM only needs to call plan_action() once.
"""
import json
import os
import traceback

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

from prompts.system2_orchestrator import SYSTEM2_ORCHESTRATOR_PROMPT
from tools.action_tools import plan_action, get_planned_actions, clear_action_log
from tools.sensor_tools import get_sensor_data, list_active_alerts
from tools.screen_tools import get_latest_screenshot

# ─── Model Configuration ─────────────────────────────────────────────────────
# All models are served by the local vLLM container via its OpenAI-compatible API.
VLLM_BASE_URL = os.getenv("LOCAL_VLLM_URL", "http://vllm_engine:8000/v1")
VLLM_API_KEY = os.getenv("LOCAL_VLLM_API_KEY", "not-needed-for-local")

# System-2 (slow, deliberate reasoning) — main orchestrator.
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-9B")

# Build a real ChatOpenAI client pointing at vLLM.
system2_llm = ChatOpenAI(
    model=ORCHESTRATOR_MODEL,
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
    temperature=float(os.getenv("ORCHESTRATOR_TEMPERATURE", "0.2")),
    max_tokens=2048,
    timeout=240.0,
)

# ─── Build the Deep Agent (FLAT — no subagents) ─────────────────────────────
# The orchestrator only has plan_action as a tool. Subagent results
# are pre-computed and injected into the user message as context.
orchestrator = create_deep_agent(
    model=system2_llm,
    system_prompt=SYSTEM2_ORCHESTRATOR_PROMPT,
    tools=[plan_action],
    subagents=[],  # No nested subagents — prevents infinite recursion
)


def _run_sensor_classification(alert: dict) -> str:
    """
    Pre-compute sensor classification (System-1) synchronously.
    Calls the same tools the subagent would have called, but directly in Python.
    """
    sensor_id = alert.get("sensor", "")
    try:
        sensor_data = get_sensor_data(sensor_id)
        alerts_data = list_active_alerts()
        return (
            f"SENSOR DATA for {sensor_id}:\n{sensor_data}\n\n"
            f"ACTIVE ALERTS:\n{alerts_data}"
        )
    except Exception as e:
        return f"Sensor classification failed: {e}"


def _run_screen_analysis() -> tuple[str, str | None]:
    """
    Pre-compute screen analysis (System-1) synchronously.
    Calls OmniParser via the get_latest_screenshot tool directly.
    Returns (text_description, image_b64_url_or_None).
    """
    try:
        result = get_latest_screenshot()
        if isinstance(result, list):
            # Multimodal format: [{"type":"text", "text": ...}, {"type":"image_url", ...}]
            text_part = ""
            image_url = None
            for item in result:
                if item.get("type") == "text":
                    text_part = item.get("text", "")
                elif item.get("type") == "image_url":
                    image_url = item.get("image_url", {}).get("url")
            return text_part, image_url
        elif isinstance(result, str):
            parsed = json.loads(result)
            return json.dumps(parsed, indent=2), None
        else:
            return str(result), None
    except Exception as e:
        return f"Screen analysis failed: {e}", None


async def run_step(
    alert: dict,
    screenshot_b64: str | None,
    action_history: list,
    step_number: int,
) -> dict:
    """
    Execute ONE step of the screenshot loop.

    v3 Architecture (Flat):
      1. Pre-compute sensor data (Python — no LLM call)
      2. Pre-compute screen analysis via OmniParser (Python — no LLM call)
      3. Inject both results as context into the orchestrator prompt
      4. The orchestrator only needs to call plan_action() — ONE LLM call

    Args:
        alert: The industrial alert dictionary
        screenshot_b64: Current screenshot from Windows client
        action_history: List of actions already executed in this cycle
        step_number: Current step index (0-based)

    Returns:
        Dict with: screen_analysis, system1, system2, vlm_prompt, llm_prompt, next_action
    """
    clear_action_log()

    # ── Step 1: Pre-compute sensor classification (System-1) ─────────────
    sensor_info = _run_sensor_classification(alert)

    # ── Step 2: Pre-compute screen analysis (System-1) ───────────────────
    screen_text, screen_image_url = _run_screen_analysis()

    # ── Step 3: Build action history context ──────────────────────────────
    if action_history:
        history_lines = "\n\nACTIONS ALREADY EXECUTED IN THIS CYCLE:\n"
        for i, item in enumerate(action_history):
            act = item.get("action", {})
            history_lines += (
                f"  Step {i + 1}: [{act.get('action_type', '?').upper()}] "
                f"{act.get('description', 'no description')}\n"
            )
    else:
        history_lines = "\n\nACTIONS ALREADY EXECUTED: None — this is the first step."

    # The VLM prompt is the high-level goal sent to the screen analyzer
    vlm_prompt = (
        f"Goal: {alert.get('task', 'Resolve the industrial alert')}. "
        f"Step {step_number + 1}. Focus on the browser or relevant industrial application."
    )

    # ── Step 4: Build the full user message with pre-computed context ─────
    user_message_text = f"""INDUSTRIAL ALERT — STEP {step_number + 1}:

TASK: {alert.get('task', 'Resolve the industrial alert')}
SEVERITY: {alert.get('severity', 'UNKNOWN')}
SENSOR: {alert.get('sensor', '?')} = {alert.get('value', '?')} {alert.get('unit', '')} (threshold: {alert.get('threshold', '?')})
LOCATION: {alert.get('location', '?')}

── SENSOR ANALYSIS (pre-computed) ──
{sensor_info}

── SCREEN ANALYSIS (pre-computed from OmniParser) ──
{screen_text}
{history_lines}

── YOUR TASK ──
Based on the sensor data and screen analysis above:
1. Determine the SINGLE NEXT action to execute on the screen.
2. Call plan_action() with EXACTLY ONE action. Use coordinates from the screen analysis.
3. If the goal is already complete, call plan_action(action_type="done").

Call plan_action() NOW.
"""

    # Build the message content (text + optional image)
    if screen_image_url:
        user_content = [
            {"type": "text", "text": user_message_text},
            {"type": "image_url", "image_url": {"url": screen_image_url}},
        ]
    else:
        user_content = user_message_text

    # The LLM prompt is what we send to the orchestrator (for UI transparency)
    llm_prompt = (
        f"Alert: {alert.get('task', '')} | "
        f"Step: {step_number + 1} | "
        f"History: {len(action_history)} actions done"
    )

    # ── Step 5: Invoke the orchestrator ──────────────────────────────────
    # With the flat architecture, the orchestrator only needs to:
    #   1. Read the pre-computed context
    #   2. Call plan_action() once
    # This should complete in 3-4 LangGraph recursions max.
    try:
        result = await orchestrator.ainvoke(
            {"messages": [{"role": "user", "content": user_content}]},
            config={"recursion_limit": 15},
        )
    except Exception as e:
        tb = traceback.format_exc()
        print(f"[orchestrator] ainvoke failed: {e}\n{tb}")
        # Fallback: return a wait action so the loop doesn't crash
        return {
            "screen_analysis": screen_text,
            "system1": sensor_info,
            "system2": f"Orchestrator error: {e}",
            "vlm_prompt": vlm_prompt,
            "llm_prompt": llm_prompt,
            "next_action": {"action_type": "wait", "seconds": 3.0,
                            "description": f"Orchestrator error — retrying. Error: {str(e)[:200]}"},
        }

    messages = result.get("messages", []) if isinstance(result, dict) else []

    # Final System-2 reasoning is the last AI message
    final_message = ""
    if messages:
        last = messages[-1]
        final_message = last.content if hasattr(last, "content") else str(last)

    # Retrieve the one action planned via plan_action tool
    planned_actions = get_planned_actions()
    next_action = (
        planned_actions[0]
        if planned_actions
        else {"action_type": "done", "description": "No action planned"}
    )

    return {
        "screen_analysis": screen_text,
        "system1": sensor_info,
        "system2": final_message,
        "vlm_prompt": vlm_prompt,
        "llm_prompt": llm_prompt,
        "next_action": next_action,
    }


# ─── Legacy: single-shot pipeline (kept for compatibility) ───────────────────
async def run_pipeline(alert: dict, screenshot_b64: str | None) -> dict:
    """
    Legacy single-shot mode: plan all actions at once.
    Superseded by run_step() in the screenshot loop.
    """
    result = await run_step(
        alert=alert,
        screenshot_b64=screenshot_b64,
        action_history=[],
        step_number=0,
    )
    return {
        "sensor_classification": result.get("system1"),
        "screen_analysis": result.get("screen_analysis"),
        "plan": result.get("system2"),
        "actions": [result.get("next_action")] if result.get("next_action") else [],
    }
