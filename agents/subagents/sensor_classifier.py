"""
System-1: Sensor Classifier Subagent
Fast, reflexive classification of industrial sensor alerts.
Uses a smaller/faster model to return results quickly.
"""
import os
from pydantic import BaseModel, Field
from ..prompts.system1_sensor import SYSTEM1_SENSOR_PROMPT
from ..tools.sensor_tools import get_sensor_data, list_active_alerts

class SensorClassification(BaseModel):
    """Structured output from the sensor classifier subagent."""
    urgency_level: str = Field(description="CRITICAL | HIGH | MEDIUM | LOW")
    alert_type: str = Field(description="THERMAL | MECHANICAL | PRESSURE | ELECTRICAL | COMMUNICATION | LEVEL | CHEMICAL")
    affected_system: str = Field(description="Name of the affected industrial system")
    estimated_root_cause: str = Field(description="Most likely cause in one sentence")
    immediate_action: str = Field(description="The single most important first action")
    requires_evacuation: bool = Field(description="Whether evacuation is needed")
    notify_roles: list[str] = Field(description="Roles to notify: MAINTENANCE, OPERATIONS, ENGINEERING, SAFETY")
    confidence: float = Field(description="Confidence score 0.0-1.0", ge=0.0, le=1.0)


# SubAgent dictionary — registered with create_deep_agent() in orchestrator.py
sensor_classifier_subagent = {
    "name": "sensor-classifier",
    "description": (
        "Rapidly classifies industrial sensor alerts. "
        "Use this FIRST when an alert arrives to determine urgency, type, root cause, and required roles. "
        "Returns a structured classification in under 3 seconds."
    ),
    "system_prompt": SYSTEM1_SENSOR_PROMPT,
    "tools": [get_sensor_data, list_active_alerts],
    # Use local Qwen model served via vLLM
    "model": os.getenv("ORCHESTRATOR_MODEL", "Qwen/Qwen3.5-27B-FP8"),
    "response_format": SensorClassification,
}
