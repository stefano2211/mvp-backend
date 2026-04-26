"""
Industrial Optimus Orchestrator
================================
The System-2 "Thinker" — the main LangChain Deep Agent that
coordinates System-1 subagents and produces the final action plan.

Supports two modes:
  - run_step(): Step-by-step screenshot loop (primary mode)
  - run_pipeline(): Legacy single-shot mode (kept for compatibility)
"""
import json
import os
import time

from deepagents import create_deep_agent

from .prompts.system2_orchestrator import SYSTEM2_ORCHESTRATOR_PROMPT
from .subagents.sensor_classifier import sensor_classifier_subagent
from .subagents.screen_analyzer import screen_analyzer_subagent

from .tools.action_tools import plan_action, get_planned_actions, clear_action_log

# ─── Model Configuration ─────────────────────────────────────────────────────
# System-2 uses Qwen running locally on vLLM.
# We configure it as an OpenAI compatible model.
os.environ["OPENAI_API_BASE"] = os.getenv("LOCAL_VLLM_URL", "http://vllm_engine:8002/v1")
os.environ["OPENAI_API_KEY"] = "not-needed-for-local"

ORCHESTRATOR_MODEL = os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-27B-FP8")

# ─── Build the Deep Agent ────────────────────────────────────────────────────
orchestrator = create_deep_agent(
    name="industrial-optimus",
    model=ORCHESTRATOR_MODEL,
    system_prompt=SYSTEM2_ORCHESTRATOR_PROMPT,
    tools=[
        plan_action,
    ],
    subagents=[
        sensor_classifier_subagent,   # System-1: fast sensor classification
        screen_analyzer_subagent,     # System-1: visual screen analysis (VLM)
    ],
)


async def run_step(
    alert: dict,
    screenshot_b64: str | None,
    action_history: list,
    step_number: int,
) -> dict:
    """
    Execute ONE step of the screenshot loop.

    The orchestrator analyzes the current screen state and action history,
    then returns EXACTLY ONE next micro-action to execute.

    Args:
        alert: The industrial alert dictionary
        screenshot_b64: Current screenshot from Windows client
        action_history: List of actions already executed in this cycle
        step_number: Current step index (0-based)

    Returns:
        Dict with: screen_analysis, system1, system2, vlm_prompt, llm_prompt, next_action
    """
    clear_action_log()

    # Build sensor info JSON
    sensor_info = json.dumps({
        "sensor_id": alert.get("sensor"),
        "current_value": alert.get("value"),
        "unit": alert.get("unit"),
        "threshold": alert.get("threshold"),
        "location": alert.get("location"),
        "severity": alert.get("severity"),
        "task_description": alert.get("task"),
    }, indent=2)

    # Build action history context for the prompt
    history_lines = ""
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

    screenshot_note = (
        "A screenshot of the current operator screen is available. "
        "Use the screen-analyzer subagent to analyze it before deciding the action."
        if screenshot_b64
        else "No screenshot is currently available from the Windows client."
    )

    # The VLM prompt is the high-level goal sent to the screen analyzer
    vlm_prompt = (
        f"Goal: {alert.get('task', 'Resolve the industrial alert')}. "
        f"Step {step_number + 1}. Focus on the browser or relevant industrial application."
    )

    # Full user message for the orchestrator
    user_message = f"""INDUSTRIAL ALERT — STEP {step_number + 1}:
{sensor_info}
{history_lines}

Screen Status: {screenshot_note}

VLM Context: {vlm_prompt}

YOUR TASK FOR THIS STEP:
1. Use the sensor-classifier subagent to review urgency and alert type.
2. Use the screen-analyzer subagent to analyze the CURRENT screen state precisely.
3. Based on the screen state and action history, determine the SINGLE NEXT action.
4. Call plan_action() with EXACTLY ONE action.
5. If the goal is already complete, call plan_action(action_type="done").
"""

    # The LLM prompt is what we send to the orchestrator (for UI transparency)
    llm_prompt = f"Alert: {alert.get('task', '')} | Step: {step_number + 1} | History: {len(action_history)} actions done"

    # Invoke the orchestrator
    result = await orchestrator.ainvoke({
        "messages": [{"role": "user", "content": user_message}]
    })

    # Extract final message text
    final_message = result["messages"][-1].content if result.get("messages") else ""

    # Retrieve the one action planned via plan_action tool
    planned_actions = get_planned_actions()
    next_action = planned_actions[0] if planned_actions else {"action_type": "done", "description": "No action planned"}

    # Try to extract structured intermediate results from the message graph
    screen_analysis = None
    system1_result = None
    try:
        for msg in result.get("messages", []):
            meta = getattr(msg, "additional_kwargs", {})
            if meta.get("subagent") == "screen-analyzer":
                screen_analysis = msg.content
            elif meta.get("subagent") == "sensor-classifier":
                system1_result = msg.content
    except Exception:
        pass

    # Fallbacks if subagent messages not captured
    if not screen_analysis:
        screen_analysis = "Screen analysis performed internally by the agent."
    if not system1_result:
        system1_result = f"Quick scan: Alert = {alert.get('task', 'unknown')}"

    return {
        "screen_analysis": screen_analysis,
        "system1": system1_result,
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
