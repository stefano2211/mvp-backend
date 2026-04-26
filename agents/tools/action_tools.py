"""
Action Tools — tools for creating and logging remediation actions.
"""
import json
import time
from typing import Optional


import contextvars

# In-memory action log for the current session, thread-safe for async contexts
_action_log_var: contextvars.ContextVar[list[dict]] = contextvars.ContextVar("_action_log")

def _get_action_log() -> list[dict]:
    try:
        return _action_log_var.get()
    except LookupError:
        l = []
        _action_log_var.set(l)
        return l


def plan_action(
    action_type: str,
    description: str,
    x: Optional[int] = None,
    y: Optional[int] = None,
    text: Optional[str] = None,
    keys: Optional[list[str]] = None,
    seconds: Optional[float] = None,
    clicks: Optional[int] = None,
) -> str:
    """
    Plan and queue a single micro-action for the Windows executor to carry out.
    
    Args:
        action_type: One of 'click', 'type', 'hotkey', 'wait', 'done'
        description: Human-readable description of what this action does
        x: X coordinate for click actions (pixels from left)
        y: Y coordinate for click actions (pixels from top)
        text: Text to type for 'type' actions
        keys: List of keys for 'hotkey' actions (e.g., ['ctrl', 's'])
        seconds: Duration in seconds for 'wait' actions
    
    Returns:
        JSON confirmation of the planned action
    """
    valid_types = {"click", "double_click", "type", "hotkey", "wait", "scroll", "done"}
    if action_type not in valid_types:
        return json.dumps({"error": f"Invalid action_type '{action_type}'. Must be one of: {valid_types}"})

    action = {
        "action_type": action_type,
        "description": description,
        "planned_at": time.strftime("%H:%M:%S"),
    }

    if action_type in ("click", "double_click"):
        if x is None or y is None:
            return json.dumps({"error": f"{action_type} action requires x and y coordinates."})
        action.update({"x": x, "y": y})

    elif action_type == "type":
        if not text:
            return json.dumps({"error": "Type action requires text parameter."})
        action.update({"text": text})

    elif action_type == "hotkey":
        if not keys:
            return json.dumps({"error": "Hotkey action requires keys list (e.g., ['ctrl', 's'])."})
        action.update({"keys": keys})

    elif action_type == "wait":
        action.update({"seconds": seconds or 1.0})

    elif action_type == "scroll":
        if clicks is None:
            return json.dumps({"error": "Scroll action requires 'clicks' parameter (positive up, negative down)."})
        action.update({"clicks": clicks, "x": x or 0, "y": y or 0})

    log = _get_action_log()
    log.append(action)
    return json.dumps({"status": "queued", "action": action, "queue_position": len(log)})


def get_planned_actions() -> list[dict]:
    """Internal helper to retrieve all planned actions from the current cycle."""
    return [a for a in _get_action_log() if a.get("action_type")]


def clear_action_log() -> None:
    """Internal helper to reset the action log for a new cycle."""
    _action_log_var.set([])
