"""
Windows Executor — Mouse & Keyboard Actions
============================================
Executes the micro-actions commanded by the Industrial Optimus agent.
Runs on the Windows host via pyautogui.

Supported action types:
  - click(x, y)         — Left-click at coordinates
  - double_click(x, y)  — Double-click at coordinates
  - type(text)          — Type a string of text (Unicode safe)
  - hotkey(keys)        — Press a keyboard shortcut (e.g., ['ctrl', 's'])
  - wait(seconds)       — Pause for N seconds
  - scroll(clicks)      — Scroll the mouse wheel
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


# ─── Resolution Scaling ──────────────────────────────────────────────────────
# OmniParser receives the 1280×720 downscaled screenshot, so all coordinates
# returned by the agent are in that space.  We need to scale them to the
# real monitor resolution before clicking.

SCREENSHOT_WIDTH = 1280
SCREENSHOT_HEIGHT = 720

# Detect the real primary monitor resolution
try:
    import mss
    with mss.mss() as sct:
        _mon = sct.monitors[1]
        REAL_WIDTH = _mon["width"]
        REAL_HEIGHT = _mon["height"]
    print(f"[Executor] Monitor: {REAL_WIDTH}x{REAL_HEIGHT}  |  Screenshot: {SCREENSHOT_WIDTH}x{SCREENSHOT_HEIGHT}")
except Exception:
    REAL_WIDTH = SCREENSHOT_WIDTH
    REAL_HEIGHT = SCREENSHOT_HEIGHT
    print("[Executor] WARNING: Could not detect monitor resolution, assuming 1280x720.")


def _scale_coord(x: int | None, y: int | None) -> tuple[int | None, int | None]:
    """Scale coordinates from screenshot space to real monitor space."""
    if x is not None:
        x = int(x * REAL_WIDTH / SCREENSHOT_WIDTH)
    if y is not None:
        y = int(y * REAL_HEIGHT / SCREENSHOT_HEIGHT)
    return x, y


def _type_text_unicode(text: str) -> None:
    """
    Type text with full Unicode support on Windows.
    pyautogui.typewrite() only handles ASCII.  For any non-ASCII characters
    we fall back to the clipboard (paste) approach using ctypes, which
    requires no extra dependencies on Windows.
    """
    try:
        text.encode("ascii")
        # Pure ASCII — typewrite is fine and gives more natural keystroke simulation
        pyautogui.typewrite(text, interval=0.05)
    except UnicodeEncodeError:
        # Unicode text — use clipboard + Ctrl+V
        try:
            import ctypes
            CF_UNICODETEXT = 13
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            user32.OpenClipboard(0)
            user32.EmptyClipboard()
            # Allocate global memory and copy the string
            hMem = kernel32.GlobalAlloc(0x0042, (len(text) + 1) * 2)
            pMem = kernel32.GlobalLock(hMem)
            ctypes.cdll.msvcrt.wcscpy(ctypes.c_wchar_p(pMem), text)
            kernel32.GlobalUnlock(hMem)
            user32.SetClipboardData(CF_UNICODETEXT, hMem)
            user32.CloseClipboard()

            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.15)
        except Exception as clip_err:
            print(f"    ⚠️  Clipboard paste failed ({clip_err}), falling back to typewrite (ASCII only)")
            pyautogui.typewrite(text, interval=0.05)


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
            x, y = _scale_coord(action.get("x"), action.get("y"))
            if x is not None and y is not None:
                # Smooth mouse movement for reliability
                pyautogui.moveTo(x, y, duration=0.3)
                time.sleep(0.1)
                pyautogui.click(x, y)
                print(f"    → Clicked at ({x}, {y})")
            else:
                print("    ⚠️  Click action missing x/y coordinates, skipping.")

        elif action_type == "double_click":
            x, y = _scale_coord(action.get("x"), action.get("y"))
            if x is not None and y is not None:
                pyautogui.doubleClick(x, y)
                print(f"    → Double-clicked at ({x}, {y})")

        elif action_type == "type":
            text = action.get("text", "")
            if text:
                _type_text_unicode(text)
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
            x, y = _scale_coord(action.get("x", 0), action.get("y", 0))
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
