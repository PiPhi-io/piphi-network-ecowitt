from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from piphi_runtime_kit_python import (
    AutomationRegistry,
    build_local_event_record,
    build_runtime_identity,
    create_runtime_starter,
)

from .contract import CAPABILITIES, COMMANDS
from .schemas import DeviceConfig
from .service import EcowittRuntimeService
from .settings import INTEGRATION_ID, INTEGRATION_NAME, INTEGRATION_VERSION

starter = create_runtime_starter(
    integration_id=INTEGRATION_ID,
    integration_name=INTEGRATION_NAME,
    version=INTEGRATION_VERSION,
)
runtime = starter.runtime
registry = starter.registry
telemetry = starter.telemetry_client
config_sync = starter.config_sync
automations = AutomationRegistry()

capabilities = CAPABILITIES
commands = COMMANDS

automations.event(
    "device.state_changed",
    label="Ecowitt state changed",
    data_schema={"capabilities": {"type": "array"}, "changed_metrics": {"type": "array"}},
)
for _event_type, _label in {
    "device.online": "Ecowitt gateway online",
    "device.offline": "Ecowitt gateway offline",
    "weather.rain_started": "Rain started",
    "weather.rain_stopped": "Rain stopped",
    "weather.lightning_detected": "Lightning detected",
    "sensor.leak_detected": "Water leak detected",
    "sensor.leak_cleared": "Water leak cleared",
}.items():
    automations.event(_event_type, label=_label, data_schema={"type": "object"})


def make_entry(config: DeviceConfig) -> dict[str, Any]:
    identity = build_runtime_identity(config, integration_id=INTEGRATION_ID)
    return {
        **identity,
        "host": config.host,
        "alias": config.alias,
        "poll_interval_seconds": config.poll_interval_seconds,
        "config": config.model_dump(),
    }


def append_runtime_event(
    event_type: str,
    device: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = build_local_event_record(
        event_type=event_type,
        device=device,
        payload=payload or {},
        source=INTEGRATION_ID,
        severity="info",
    )
    registry.append_event(event)
    return event


def get_entry_or_404(config_id: str) -> dict[str, Any]:
    entry = registry.get(config_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"unknown config_id={config_id}")
    return entry


async def apply_config(config: DeviceConfig) -> None:
    entry = make_entry(config)
    registry.set(config.id, entry)
    try:
        await ecowitt_service.configure(config, entry)
    except Exception:
        registry.remove(config.id)
        raise
    append_runtime_event(
        "runtime.config.applied",
        entry,
        {"host": config.host, "alias": config.alias},
    )


async def remove_config(config_id: str) -> bool:
    await ecowitt_service.remove(config_id)
    entry = registry.remove(config_id)
    if entry is None:
        return False
    append_runtime_event(
        "runtime.config.removed",
        entry,
        {"host": entry.get("host"), "alias": entry.get("alias")},
    )
    return True


def _register_automation_actions() -> None:
    async def refresh(request: Any) -> dict[str, Any]:
        target = request.target if isinstance(request.target, dict) else {}
        config_id = str(request.config_id or target.get("config_id") or "")
        if not config_id:
            raise HTTPException(status_code=400, detail="refresh requires config_id")
        state = await ecowitt_service.refresh(config_id)
        return {
            "command": "refresh",
            "config_id": config_id,
            "device_id": str(request.device_id or target.get("device_id") or config_id),
            "sensor_count": state["sensor_count"],
            "connected": state["connected"],
        }

    automations.action("refresh", label="Refresh Ecowitt readings")(refresh)


ecowitt_service = EcowittRuntimeService(
    registry=registry,
    runtime=runtime,
    telemetry=telemetry,
    event_client=starter.event_client,
    record_event=registry.append_event,
)

_register_automation_actions()
