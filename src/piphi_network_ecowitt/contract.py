from __future__ import annotations

from typing import Any

ENDPOINTS = {
    "health": "/health",
    "diagnostics": "/diagnostics",
    "discover": "/discover",
    "entities": "/entities",
    "state": "/state",
    "config": "/config",
    "config_sync": "/config/sync",
    "deconfigure": "/deconfigure",
    "ui_config": "/ui-config",
    "events": "/events",
    "command": "/command",
}
REQUIRED_ENDPOINTS = ["health", "entities", "command", "config", "ui_config"]


def sensor(unit: str, *widgets: str) -> dict[str, Any]:
    allowed = list(widgets or ("stat", "line-chart"))
    return {
        "kind": "sensor",
        "unit": unit,
        "dashboard": {"allowed_widgets": allowed, "default_widget": allowed[0]},
    }


CAPABILITIES: dict[str, dict[str, Any]] = {
    "connected": sensor("bool", "tile", "status-list"),
    "temperature_c": sensor("C", "external-widget", "stat", "line-chart"),
    "indoor_temperature_c": sensor("C", "external-widget", "stat", "line-chart"),
    "dew_point_c": sensor("C"),
    "wind_chill_c": sensor("C"),
    "heat_index_c": sensor("C"),
    "humidity_percent": sensor("%", "external-widget", "gauge", "line-chart"),
    "indoor_humidity_percent": sensor("%", "gauge", "line-chart"),
    "absolute_pressure_hpa": sensor("hPa"),
    "pressure_hpa": sensor("hPa", "external-widget", "stat", "line-chart"),
    "wind_direction_deg": sensor("deg", "external-widget", "stat"),
    "wind_speed_ms": sensor("m/s", "external-widget", "stat", "line-chart"),
    "wind_gust_ms": sensor("m/s", "external-widget", "stat", "line-chart"),
    "daily_max_wind_ms": sensor("m/s"),
    "rain_event_mm": sensor("mm"),
    "rain_rate_mmh": sensor("mm/h", "external-widget", "stat", "line-chart"),
    "rain_daily_mm": sensor("mm", "external-widget", "stat", "line-chart"),
    "rain_weekly_mm": sensor("mm"),
    "rain_monthly_mm": sensor("mm"),
    "rain_yearly_mm": sensor("mm"),
    "rain_total_mm": sensor("mm"),
    "piezo_rain_event_mm": sensor("mm"),
    "piezo_rain_rate_mmh": sensor("mm/h"),
    "piezo_rain_daily_mm": sensor("mm"),
    "piezo_rain_weekly_mm": sensor("mm"),
    "piezo_rain_monthly_mm": sensor("mm"),
    "piezo_rain_yearly_mm": sensor("mm"),
    "piezo_rain_total_mm": sensor("mm"),
    "solar_irradiance_wm2": sensor("W/m2", "external-widget", "stat", "line-chart"),
    "uv_index": sensor("index", "external-widget", "gauge", "line-chart"),
    "soil_moisture_percent": sensor("%", "gauge", "line-chart"),
    "leaf_wetness_percent": sensor("%", "gauge", "line-chart"),
    "leak_detected": sensor("bool", "tile", "status-list"),
    "pm1_ugm3": sensor("ug/m3"),
    "pm25_ugm3": sensor("ug/m3", "gauge", "line-chart"),
    "pm4_ugm3": sensor("ug/m3"),
    "pm10_ugm3": sensor("ug/m3", "gauge", "line-chart"),
    "co2_ppm": sensor("ppm", "gauge", "line-chart"),
    "battery_level": sensor("level", "stat"),
    "battery_voltage_v": sensor("V", "stat", "line-chart"),
    "depth_mm": sensor("mm", "gauge", "line-chart"),
    "air_gap_mm": sensor("mm", "gauge", "line-chart"),
    "lightning_distance_km": sensor("km", "stat", "line-chart"),
    "lightning_count": sensor("count", "stat", "line-chart"),
    "refresh": {
        "kind": "action",
        "dashboard": {"allowed_widgets": ["button"], "default_widget": "button"},
    },
}

COMMANDS: dict[str, dict[str, Any]] = {
    "refresh": {
        "description": "Fetch fresh readings from the configured Ecowitt gateway.",
        "timeout_ms": 15000,
    }
}

CONFIG_SCHEMA: dict[str, Any] = {
    "schema": {
        "title": "Ecowitt Gateway Setup",
        "type": "object",
        "required": ["host"],
        "properties": {
            "host": {
                "type": "string",
                "title": "Gateway address",
                "description": "Ecowitt gateway IP address or HTTP(S) origin on the same network.",
            },
            "alias": {"type": "string", "title": "Display name"},
            "poll_interval_seconds": {
                "type": "integer",
                "title": "Poll interval (seconds)",
                "default": 60,
                "minimum": 15,
                "maximum": 3600,
            },
            "request_timeout_seconds": {
                "type": "number",
                "title": "Request timeout (seconds)",
                "default": 5,
                "minimum": 1,
                "maximum": 15,
            },
        },
    },
    "uiSchema": {
        "host": {"placeholder": "192.168.1.50"},
        "alias": {"placeholder": "Backyard Weather Station"},
        "poll_interval_seconds": {"ui:widget": "updown"},
        "request_timeout_seconds": {"ui:widget": "updown"},
    },
}

FALLBACK_ENTITY: dict[str, Any] = {
    "id": "ecowitt-gateway",
    "name": "Ecowitt Weather Gateway",
    "device_id": "ecowitt-gateway",
    "entity_type": "sensor",
    "device_class": "weather_station",
    "capabilities": ["connected", "temperature_c", "humidity_percent", "refresh"],
    "available_commands": [{"id": "refresh", "label": "Refresh", "kind": "action"}],
    "dashboard": {
        "allowed_widgets": ["external-widget", "tile", "stat"],
        "default_widget": "external-widget",
        "recommended_widgets": ["external-widget"],
    },
}
