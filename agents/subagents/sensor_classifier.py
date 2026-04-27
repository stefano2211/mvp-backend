"""
System-1: Sensor Classifier Subagent
Fast, reflexive classification of industrial sensor alerts.
Uses a smaller/faster model to return results quickly.
"""
import os

from pydantic import BaseModel, Field
from langchain_openai import ChatOpenAI

from prompts.system1_sensor import SYSTEM1_SENSOR_PROMPT
from tools.sensor_tools import get_sensor_data, list_active_alerts


class SensorClassification(BaseModel):
    """Structured output from the sensor classifier subagent."""
    reasoning: str = Field(description="2-3 sentences explaining the classification logic based on retrieved sensor data")
    urgency_level: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    alert_type: str = Field(description="THERMAL | MECHANICAL | PRESSURE | ELECTRICAL | COMMUNICATION | LEVEL | CHEMICAL")
    affected_system: str = Field(description="Name of the affected industrial system")
    estimated_root_cause: str = Field(description="Most likely cause in one sentence")
    immediate_action: str = Field(description="The single most important first action")
    requires_evacuation: bool = Field(description="Whether evacuation is needed — true only for imminent danger to personnel")
    notify_roles: list[str] = Field(description="Subset of: MAINTENANCE, OPERATIONS, ENGINEERING, SAFETY")
    confidence: float = Field(description="Confidence score 0.0-1.0 — lower if data is anomalous or sensor may be malfunctioning", ge=0.0, le=1.0)


# ── Sensor classifier model (System-1: Fast Intuition) ──────────────────────
# Configurable separately from System-2; defaults to the same model so the MVP
# can run on a single-GPU deployment.
SYSTEM1_MODEL = os.getenv("SYSTEM1_MODEL", os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-27B-FP8"))
VLLM_BASE_URL = os.getenv("LOCAL_VLLM_URL", "http://vllm_engine:8000/v1")
VLLM_API_KEY = os.getenv("LOCAL_VLLM_API_KEY", "not-needed-for-local")

sensor_llm = ChatOpenAI(
    model=SYSTEM1_MODEL,
    base_url=VLLM_BASE_URL,
    api_key=VLLM_API_KEY,
    temperature=float(os.getenv("SYSTEM1_TEMPERATURE", "0.1")),
    timeout=60.0,
)

# SubAgent dictionary — registered with create_deep_agent() in orchestrator.py
sensor_classifier_subagent = {
    "name": "sensor-classifier",
    "description": (
        "Rapidly classifies industrial sensor alerts. "
        "Use this FIRST when an alert arrives to determine urgency, type, "
        "root cause, and required roles. Returns a structured classification."
    ),
    "system_prompt": SYSTEM1_SENSOR_PROMPT,
    "tools": [get_sensor_data, list_active_alerts],
    "model": sensor_llm,
    "response_format": SensorClassification,
}
