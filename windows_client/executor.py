"""
Windows Executor — Mouse & Keyboard Actions
============================================
Executes the micro-actions commanded by the Industrial Optimus agent.
Runs on the Windows host via pyautogui.

Supported action types:
  - click(x, y)         — Left-click at coordinates
  - type(text)          — Type a string of text
  - hotkey(keys)        — Press a keyboard shortcut (e.g., ['ctrl', 's'])
  - wait(seconds)       — Pause for N seconds
  - done                — No-op: signals end of cycle
"""
import time

try:
    import pyautogui

    # Safety settings
    pyautogui.FAILSAFE = True   # Move mouse to top-left corner to abort
    pyautogui.PAUSE = 0.05      # Small pause between each pyautogui call
    PYAUTOGUI_AVAILABLE = True
    print("[Executor] pyautogui loaded — live execution enabled.")
except ImportError:
    PYAUTOGUI_AVAILABLE = False
    print("[Executor] WARNING: pyautogui not installed — running in DRY RUN mode.")


def _dry_run_log(action: dict) -> None:
    """Log actions when pyautogui is not available (dry run mode)."""
    print(f"  [DRY RUN] Would execute: {action}")


def execute_action(action: dict) -> None:
    """
    Execute a single micro-action on the Windows desktop.
    
    Args:
        action: Dictionary containing action_type and parameters.
    """
    action_type = action.get("action_type", "wait")
    description = action.get("description", "")

    print(f"  🎯 Executing: [{action_type.upper()}] {description}")

    if not PYAUTOGUI_AVAILABLE:
        _dry_run_log(action)
        return

    try:
        if action_type == "click":
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                # Smooth mouse movement for reliability
                pyautogui.moveTo(x, y, duration=0.3)
                time.sleep(0.1)
                pyautogui.click(x, y)
                print(f"    → Clicked at ({x}, {y})")
            else:
                print("    ⚠️  Click action missing x/y coordinates, skipping.")

        elif action_type == "double_click":
            x = action.get("x")
            y = action.get("y")
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y)
                print(f"    → Double-clicked at ({x}, {y})")

        elif action_type == "type":
            text = action.get("text", "")
            if text:
                pyautogui.typewrite(text, interval=0.05)
                print(f"    → Typed: '{text}'")

        elif action_type == "hotkey":
            keys = action.get("keys", [])
            if keys:
                pyautogui.hotkey(*keys)
                print(f"    → Hotkey: {'+'.join(keys)}")

        elif action_type == "wait":
            seconds = float(action.get("seconds", 1.0))
            time.sleep(seconds)
            print(f"    → Waited {seconds}s")

        elif action_type == "scroll":
            x = action.get("x", 0)
            y = action.get("y", 0)
            clicks = action.get("clicks", 3)
            pyautogui.scroll(clicks, x=x, y=y)
            print(f"    → Scrolled {clicks} at ({x}, {y})")

        elif action_type == "done":
            print("    → Cycle complete.")

        else:
            print(f"    ⚠️  Unknown action type: '{action_type}', skipping.")

    except pyautogui.FailSafeException:
        print("  🛑 FAILSAFE TRIGGERED — Mouse moved to top-left corner. Aborting actions.")
        raise
    except Exception as e:
        print(f"  ❌ Action failed: {e}")
