"""
Industrial Optimus Orchestrator
================================
The System-2 "Thinker" — produces the final action plan.

Architecture (v4 — Direct LLM Call):
  We bypass LangGraph entirely to avoid GraphRecursionError.
  Instead of a ReAct agent loop, we:
    1. Pre-compute sensor + screen analysis in Python
    2. Make ONE direct ChatOpenAI call with tools bound
    3. Extract the tool call from the response
  This guarantees exactly 1 LLM call per step — zero recursion.
"""
import json
import os
import traceback

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from prompts.system2_orchestrator import SYSTEM2_ORCHESTRATOR_PROMPT
from tools.action_tools import plan_action, get_planned_actions, clear_action_log
from tools.sensor_tools import get_sensor_data, list_active_alerts
from tools.screen_tools import get_latest_screenshot

# ─── Model Configuration ─────────────────────────────────────────────────────
VLLM_BASE_URL = os.getenv("LOCAL_VLLM_URL", "http://vllm_engine:8000/v1")
VLLM_API_KEY = os.getenv("LOCAL_VLLM_API_KEY", "not-needed-for-local")
ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-9B")

system2_llm = ChatOpenAI(
    model=ORCHESTRATOR_MODEL,
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
    temperature=float(os.getenv("ORCHESTRATOR_TEMPERATURE", "0.6")),
    max_tokens=2048,
    timeout=240.0,
)

# Bind the plan_action tool so the LLM knows its schema
llm_with_tools = system2_llm.bind_tools([plan_action])


def _run_sensor_classification(alert: dict) -> str:
    """Pre-compute sensor classification (System-1) synchronously."""
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
    """Pre-compute screen analysis (System-1) synchronously."""
    try:
        result = get_latest_screenshot()
        if isinstance(result, list):
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


def _execute_tool_call(tool_call: dict) -> dict:
    """Execute the plan_action tool call and return the action dict."""
    args = tool_call.get("args", {})
    # Call plan_action directly
    result_str = plan_action(**args)
    result = json.loads(result_str)
    if "error" in result:
        return {"action_type": "wait", "seconds": 2.0,
                "description": f"Tool error: {result['error']}"}
    return result.get("action", {"action_type": "done", "description": "Action planned"})


async def run_step(
    alert: dict,
    screenshot_b64: str | None,
    action_history: list,
    step_number: int,
) -> dict:
    """
    Execute ONE step of the screenshot loop.

    v4 Architecture (Direct LLM — no LangGraph):
      1. Pre-compute sensor data (Python)
      2. Pre-compute screen analysis via OmniParser (Python)
      3. Make ONE direct LLM call with tools bound
      4. Extract tool call → execute plan_action → return

    Zero recursion. Zero LangGraph. One LLM call.
    """
    clear_action_log()

    # ── Step 1: Pre-compute sensor classification ─────────────────────────
    sensor_info = _run_sensor_classification(alert)

    # ── Step 2: Pre-compute screen analysis ───────────────────────────────
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

    vlm_prompt = (
        f"Goal: {alert.get('task', 'Resolve the industrial alert')}. "
        f"Step {step_number + 1}. Focus on the browser or relevant industrial application."
    )

    # ── Step 4: Build the full user message ───────────────────────────────
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

You MUST call plan_action() NOW. Do not explain, just call the tool.
"""

    # Build messages
    messages = [
        SystemMessage(content=SYSTEM2_ORCHESTRATOR_PROMPT),
    ]

    if screen_image_url:
        messages.append(HumanMessage(content=[
            {"type": "text", "text": user_message_text},
            {"type": "image_url", "image_url": {"url": screen_image_url}},
        ]))
    else:
        messages.append(HumanMessage(content=user_message_text))

    llm_prompt = (
        f"Alert: {alert.get('task', '')} | "
        f"Step: {step_number + 1} | "
        f"History: {len(action_history)} actions done"
    )

    # ── Step 5: ONE direct LLM call — no LangGraph, no loops ─────────────
    try:
        print(f"[orchestrator] Calling LLM directly (step {step_number + 1})...")
        response = await llm_with_tools.ainvoke(messages)
        print(f"[orchestrator] LLM responded. Tool calls: {len(response.tool_calls) if response.tool_calls else 0}")

        # Extract reasoning text
        reasoning = ""
        if isinstance(response.content, str):
            reasoning = response.content.strip()
        elif isinstance(response.content, list):
            # Sometimes content is a list of dicts with type/text
            for part in response.content:
                if isinstance(part, dict) and part.get("type") == "text":
                    reasoning += part.get("text", "")
                elif isinstance(part, str):
                    reasoning += part

        # Extract tool calls
        if response.tool_calls:
            tc = response.tool_calls[0]
            print(f"[orchestrator] Tool call: {tc['name']}({json.dumps(tc['args'])[:200]})")

            # Execute the tool call
            next_action = _execute_tool_call(tc)

            if not reasoning:
                reasoning = f"[Action: {tc['name']}({json.dumps(tc['args'])[:300]})]"
        else:
            # LLM didn't call the tool — try to parse action from text
            print(f"[orchestrator] WARNING: LLM did not call plan_action. Response: {str(response.content)[:300]}")

            # Fallback: if on step 1 and we see a Google consent page, click "Reject all"
            if "Before you continue" in screen_text or "consent" in screen_text.lower():
                next_action = {"action_type": "click", "x": 640, "y": 400,
                               "description": "Clicking to dismiss Google consent dialog"}
            else:
                next_action = {"action_type": "wait", "seconds": 2.0,
                               "description": "LLM did not produce a tool call — waiting"}

            if not reasoning:
                reasoning = "LLM responded without calling plan_action tool."

    except Exception as e:
        tb = traceback.format_exc()
        print(f"[orchestrator] LLM call failed: {e}\n{tb}")
        return {
            "screen_analysis": screen_text,
            "system1": sensor_info,
            "system2": f"LLM error: {e}",
            "vlm_prompt": vlm_prompt,
            "llm_prompt": llm_prompt,
            "next_action": {"action_type": "wait", "seconds": 3.0,
                            "description": f"LLM error — retrying. Error: {str(e)[:200]}"},
        }

    return {
        "screen_analysis": screen_text,
        "system1": sensor_info,
        "system2": reasoning,
        "vlm_prompt": vlm_prompt,
        "llm_prompt": llm_prompt,
        "next_action": next_action,
    }


# ─── Legacy: single-shot pipeline (kept for compatibility) ───────────────────
async def run_pipeline(alert: dict, screenshot_b64: str | None) -> dict:
    """Legacy single-shot mode."""
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
