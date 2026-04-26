"""
Sensor Tools — tools used by the sensor-classifier subagent and orchestrator.
"""
import json
from typing import Any


def get_sensor_data(sensor_id: str) -> str:
    """
    Retrieve current and historical data for a specific industrial sensor.
    Returns a JSON string with sensor readings and thresholds.
    
    Args:
        sensor_id: The unique identifier of the sensor (e.g., 'TEMP-003', 'VIB-A2')
    """
    # Simulated sensor database
    sensor_db: dict[str, dict[str, Any]] = {
        "TEMP-003": {
            "id": "TEMP-003",
            "name": "Temperature Sensor — Pump #3",
            "current_value": 98.4,
            "unit": "°C",
            "normal_range": {"min": 20.0, "max": 85.0},
            "critical_threshold": 95.0,
            "location": "Sala de Bombas - Sector B",
            "last_maintenance": "2026-01-15",
            "history_1h": [72.1, 75.3, 80.2, 85.4, 88.1, 92.3, 95.1, 98.4],
        },
        "VIB-A2": {
            "id": "VIB-A2",
            "name": "Vibration Sensor — Motor A2",
            "current_value": 15.8,
            "unit": "mm/s",
            "normal_range": {"min": 0.0, "max": 7.1},
            "critical_threshold": 14.2,
            "location": "Línea de Producción A",
            "last_maintenance": "2025-12-20",
            "history_1h": [3.2, 3.5, 4.1, 5.8, 7.9, 10.2, 13.1, 15.8],
        },
        "PRES-P07": {
            "id": "PRES-P07",
            "name": "Pressure Sensor — Pipeline P-07",
            "current_value": 142.3,
            "unit": "PSI",
            "normal_range": {"min": 80.0, "max": 120.0},
            "critical_threshold": 135.0,
            "location": "Sector C - Planta Principal",
            "last_maintenance": "2026-02-10",
            "history_1h": [102.1, 108.3, 115.2, 122.4, 128.1, 135.3, 139.1, 142.3],
        },
        "COMM-PLC-C": {
            "id": "COMM-PLC-C",
            "name": "Communication Status — PLC Sector C",
            "current_value": 0,
            "unit": "status (1=OK, 0=FAIL)",
            "normal_range": {"min": 1, "max": 1},
            "critical_threshold": 0,
            "location": "Panel de Control - Sector C",
            "last_maintenance": "2026-03-01",
            "history_1h": [1, 1, 1, 1, 1, 1, 0, 0],
        },
        "LEVEL-T01": {
            "id": "LEVEL-T01",
            "name": "Level Sensor — Tank T-01",
            "current_value": 12.5,
            "unit": "%",
            "normal_range": {"min": 20.0, "max": 95.0},
            "critical_threshold": 10.0,
            "location": "Área de Almacenamiento",
            "last_maintenance": "2026-01-28",
            "history_1h": [45.2, 40.1, 35.8, 30.2, 25.4, 20.1, 16.3, 12.5],
        },
    }

    sensor = sensor_db.get(sensor_id)
    if not sensor:
        return json.dumps({"error": f"Sensor '{sensor_id}' not found in database."})
    
    # Calculate deviation percentage
    threshold = sensor["normal_range"]["max"]
    deviation_pct = ((sensor["current_value"] - threshold) / threshold * 100) if threshold != 0 else 0
    sensor["deviation_from_threshold_pct"] = round(deviation_pct, 2)
    sensor["trend"] = "RISING" if sensor["history_1h"][-1] > sensor["history_1h"][-2] else "FALLING"
    
    return json.dumps(sensor)


def list_active_alerts() -> str:
    """
    List all currently active sensor alerts across the plant.
    Returns a JSON string with all alerts sorted by severity.
    """
    alerts = [
        {"sensor_id": "TEMP-003", "severity": "CRITICAL", "value": 98.4, "unit": "°C"},
        {"sensor_id": "VIB-A2", "severity": "HIGH", "value": 15.8, "unit": "mm/s"},
        {"sensor_id": "PRES-P07", "severity": "CRITICAL", "value": 142.3, "unit": "PSI"},
    ]
    return json.dumps({"active_alerts": alerts, "total": len(alerts)})
