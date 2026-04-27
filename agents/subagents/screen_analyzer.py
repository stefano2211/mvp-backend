"""
System-1: Screen Analyzer Subagent
Visual analysis of the current Windows host screenshot.
Uses a multimodal model (VLM) capable of interpreting images.
"""
import os
from typing import Optional

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from prompts.system1_screen import SYSTEM1_SCREEN_PROMPT
from tools.screen_tools import get_latest_screenshot


class UIElement(BaseModel):
    """A detected interactive element on the screen."""
    element: str = Field(description="Name or label of the element")
    type: str = Field(description="button | input | menu | link | icon | text")
    approximate_x: int = Field(description="Approximate X coordinate in pixels (from OmniParser center_x)")
    approximate_y: int = Field(description="Approximate Y coordinate in pixels (from OmniParser center_y)")
    omniparser_id: Optional[int] = Field(
        default=None,
        description="OmniParser Set-of-Marks numeric ID drawn on top of this element, if available",
    )


class ScreenAnalysis(BaseModel):
    """Structured output from the screen analyzer subagent."""
    current_application: str = Field(description="Name of the application currently in focus")
    screen_description: str = Field(description="Paragraph describing what is visible on screen")
    interactive_elements: list[UIElement] = Field(description="List of visible interactive elements")
    is_loading: bool = Field(description="Whether the screen appears to be loading")
    has_error_dialog: bool = Field(description="Whether an error dialog is visible")
    error_dialog_text: Optional[str] = Field(default=None, description="Text of any error dialog")
    recommended_next_ui_action: str = Field(description="What the agent should do next on this screen")


# ── Vision model (System-1: Fast Intuition) ─────────────────────────────────
# Per architecture spec: System-1 SHOULD be a smaller/faster model for quick
# visual scanning. It is configurable via the SYSTEM1_MODEL env var; if unset,
# it falls back to the same model as System-2 (single-GPU deployments).
SYSTEM1_MODEL = os.getenv("SYSTEM1_MODEL", os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-27B-FP8"))
VLLM_BASE_URL = os.getenv("LOCAL_VLLM_URL", "http://vllm_engine:8002/v1")
VLLM_API_KEY = os.getenv("LOCAL_VLLM_API_KEY", "not-needed-for-local")

screen_vlm = ChatOpenAI(
    model=SYSTEM1_MODEL,
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
    temperature=float(os.getenv("SYSTEM1_TEMPERATURE", "0.1")),
    timeout=120.0,
)

# SubAgent dictionary — registered with create_deep_agent() in orchestrator.py
screen_analyzer_subagent = {
    "name": "screen-analyzer",
    "description": (
        "Analyzes the current OmniParser-annotated screenshot of the operator's "
        "Windows screen. Use this to understand what application is open, what UI "
        "elements are visible, and what the next screen interaction should be. "
        "Returns a structured analysis with element coordinates lifted from "
        "OmniParser's Set-of-Marks output."
    ),
    "system_prompt": SYSTEM1_SCREEN_PROMPT,
    "tools": [get_latest_screenshot],
    "model": screen_vlm,
    "response_format": ScreenAnalysis,
}
