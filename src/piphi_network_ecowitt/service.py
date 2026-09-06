from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException
from piphi_runtime_kit_python import schedule_event_delivery, schedule_telemetry_delivery

from .ecowitt import EcowittHttpClient, EcowittSensor, EcowittSnapshot
from .schemas import DeviceConfig
from .settings import INTEGRATION_ID


@dataclass(slots=True)
class ActiveGateway:
    config: DeviceConfig
    entry: dict[str, Any]
    client: EcowittHttpClient
    poll_task: asyncio.Task[None] | None = None
    previous_gateway: dict[str, bool | float | int] | None = None
    previous_sensors: dict[str, dict[str, bool | float | int]] = field(default_factory=dict)
    sensors: tuple[EcowittSensor, ...] = ()
    last_error: str | None = None


ClientFactory = Callable[[DeviceConfig], EcowittHttpClient]


def default_client_factory(config: DeviceConfig) -> EcowittHttpClient:
    return EcowittHttpClient(config.host, timeout_seconds=config.request_timeout_seconds)


class EcowittRuntimeService:
    def __init__(
        self,
        *,
        registry: Any,
        runtime: Any,
        telemetry: Any,
        event_client: Any,
        record_event: Callable[[dict[str, Any]], Any],
        client_factory: ClientFactory = default_client_factory,
    ) -> None:
        self.registry = registry
        self.runtime = runtime
        self.telemetry = telemetry
        self.event_client = event_client
        self.record_event = record_event
        self.client_factory = client_factory
        self._active: dict[str, ActiveGateway] = {}
        self._lock = asyncio.Lock()

    @property
    def active_config_ids(self) -> list[str]:
        return sorted(self._active)

    async def configure(self, config: DeviceConfig, entry: dict[str, Any]) -> dict[str, Any]:
        client = self.client_factory(config)
        try:
            snapshot = await client.read_snapshot()
        except Exception:
            await client.close()
            raise
        config_id = str(entry["config_id"])
        async with self._lock:
            previous = self._active.pop(config_id, None)
            if previous is not None:
                await self._stop(previous)
            active = ActiveGateway(config=config, entry=entry, client=client)
            self._active[config_id] = active
            state = self._apply_snapshot(active, snapshot)
            active.poll_task = asyncio.create_task(
                self._poll_loop(active), name=f"ecowitt-poller-{config_id}"
            )
            return state

    async def refresh(self, config_id: str) -> dict[str, Any]:
        active = self._active.get(str(config_id))
        if active is None:
            raise HTTPException(status_code=404, detail=f"unknown config_id={config_id}")
        try:
            snapshot = await active.client.read_snapshot()
        except Exception as exc:
            self._mark_offline(active, exc)
            raise
        return self._apply_snapshot(active, snapshot)

    async def remove(self, config_id: str) -> bool:
        async with self._lock:
            active = self._active.pop(str(config_id), None)
            if active is None:
                return False
            await self._stop(active)
            return True

    async def close(self) -> None:
        async with self._lock:
            active_gateways = list(self._active.values())
            self._active.clear()
            for active in active_gateways:
                await self._stop(active)

    def entities(self) -> list[dict[str, Any]]:
        entities: list[dict[str, Any]] = []
        for active in self._active.values():
            gateway_id = str(active.entry["device_id"])
            entities.append(
                {
                    "id": gateway_id,
                    "name": active.config.alias or "Ecowitt Weather Gateway",
                    "config_id": active.entry["config_id"],
                    "device_id": gateway_id,
                    "entity_type": "sensor",
                    "device_class": "weather_station",
                    "capabilities": sorted(
                        set(active.previous_gateway or {}) | {"connected", "refresh"}
                    ),
                    "available_commands": [{"id": "refresh", "label": "Refresh", "kind": "action"}],
                    "dashboard": {
                        "allowed_widgets": ["external-widget", "tile", "stat", "line-chart"],
                        "default_widget": "external-widget",
                        "recommended_widgets": ["external-widget"],
                    },
                    "metadata": {"host": active.config.host},
                }
            )
            for sensor in active.sensors:
                device_id = self.sensor_device_id(active, sensor)
                entities.append(
                    {
                        "id": device_id,
                        "name": sensor.name,
                        "config_id": active.entry["config_id"],
                        "device_id": device_id,
                        "parent_device_id": gateway_id,
                        "entity_type": "sensor",
                        "device_class": sensor.sensor_type,
                        "capabilities": sorted(sensor.metrics),
                        "available_commands": [],
                        "dashboard": {
                            "allowed_widgets": [
                                "external-widget",
                                "stat",
                                "line-chart",
                                "gauge",
                                "tile",
                            ],
                            "default_widget": "stat",
                        },
                        "metadata": {"sensor_type": sensor.sensor_type, "channel": sensor.channel},
                    }
                )
        return entities

    def diagnostics(self) -> dict[str, Any]:
        return {
            config_id: {
                "host": active.config.host,
                "poll_interval_seconds": active.config.poll_interval_seconds,
                "sensor_count": len(active.sensors),
                "last_error": active.last_error,
                "poll_task_active": bool(active.poll_task and not active.poll_task.done()),
            }
            for config_id, active in self._active.items()
        }

    async def _poll_loop(self, active: ActiveGateway) -> None:
        while True:
            try:
                await asyncio.sleep(active.config.poll_interval_seconds)
                snapshot = await active.client.read_snapshot()
                self._apply_snapshot(active, snapshot)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 - a poller must survive transport failures
                self._mark_offline(active, exc)

    async def _stop(self, active: ActiveGateway) -> None:
        if active.poll_task is not None and active.poll_task is not asyncio.current_task():
            active.poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await active.poll_task
        await active.client.close()

    def _apply_snapshot(self, active: ActiveGateway, snapshot: EcowittSnapshot) -> dict[str, Any]:
        was_offline = active.last_error is not None
        previous_gateway = active.previous_gateway
        active.last_error = None
        active.sensors = snapshot.sensors
        gateway_state: dict[str, Any] = {
            **snapshot.gateway_metrics,
            "host": active.config.host,
            "sensor_count": len(snapshot.sensors),
            "raw_sections": list(snapshot.raw_sections),
            "sensors": [
                {
                    "device_id": self.sensor_device_id(active, sensor),
                    "name": sensor.name,
                    "sensor_type": sensor.sensor_type,
                    "channel": sensor.channel,
                    "metrics": sensor.metrics,
                }
                for sensor in snapshot.sensors
            ],
        }
        config_id = str(active.entry["config_id"])
        gateway_id = str(active.entry["device_id"])
        self.registry.update_state(config_id, gateway_state, device_id=gateway_id)
        self._send_telemetry(active, gateway_id, snapshot.gateway_metrics, snapshot.gateway_units)
        if previous_gateway is not None:
            self._emit_gateway_transitions(active, previous_gateway, snapshot.gateway_metrics)
        if was_offline:
            self._emit(active, "device.online", gateway_id, {"host": active.config.host}, "info")
        for sensor in snapshot.sensors:
            device_id = self.sensor_device_id(active, sensor)
            self._send_telemetry(active, device_id, sensor.metrics, sensor.units)
            previous = active.previous_sensors.get(sensor.sensor_id)
            if previous is not None:
                self._emit_sensor_transitions(active, sensor, previous)
            active.previous_sensors[sensor.sensor_id] = dict(sensor.metrics)
        active.previous_gateway = dict(snapshot.gateway_metrics)
        return gateway_state

    def _mark_offline(self, active: ActiveGateway, exc: Exception) -> None:
        first_failure = active.last_error is None
        active.last_error = str(exc)
        self.registry.update_state(
            str(active.entry["config_id"]),
            {"connected": False, "error": str(exc)},
            device_id=str(active.entry["device_id"]),
        )
        if first_failure and active.previous_gateway is not None:
            self._emit(
                active,
                "device.offline",
                str(active.entry["device_id"]),
                {"host": active.config.host, "reason": str(exc)},
                "warning",
            )

    def _send_telemetry(
        self,
        active: ActiveGateway,
        device_id: str,
        metrics: dict[str, bool | float | int],
        units: dict[str, str],
    ) -> None:
        schedule_telemetry_delivery(
            process_state=self.runtime.process_state,
            telemetry_client=self.telemetry,
            auth_context=self.runtime.auth,
            config_id=str(active.entry["config_id"]),
            device_id=device_id,
            container_id=active.entry.get("container_id"),
            metrics=metrics,
            units=units,
        )

    def _emit_gateway_transitions(
        self,
        active: ActiveGateway,
        previous: dict[str, bool | float | int],
        current: dict[str, bool | float | int],
    ) -> None:
        before = float(previous.get("rain_rate_mmh", 0) or 0)
        after = float(current.get("rain_rate_mmh", 0) or 0)
        if before <= 0 < after:
            self._emit(
                active,
                "weather.rain_started",
                str(active.entry["device_id"]),
                {"rain_rate_mmh": after},
                "info",
            )
        elif before > 0 >= after:
            self._emit(active, "weather.rain_stopped", str(active.entry["device_id"]), {}, "info")

    def _emit_sensor_transitions(
        self,
        active: ActiveGateway,
        sensor: EcowittSensor,
        previous: dict[str, bool | float | int],
    ) -> None:
        device_id = self.sensor_device_id(active, sensor)
        if (
            "leak_detected" in sensor.metrics
            and previous.get("leak_detected") != sensor.metrics["leak_detected"]
        ):
            detected = bool(sensor.metrics["leak_detected"])
            self._emit(
                active,
                "sensor.leak_detected" if detected else "sensor.leak_cleared",
                device_id,
                {"channel": sensor.channel},
                "critical" if detected else "info",
            )
        before = int(previous.get("lightning_count", 0) or 0)
        after = int(sensor.metrics.get("lightning_count", 0) or 0)
        if after > before:
            self._emit(
                active,
                "weather.lightning_detected",
                device_id,
                {
                    "count_delta": after - before,
                    "distance_km": sensor.metrics.get("lightning_distance_km"),
                },
                "warning",
            )

    def _emit(
        self,
        active: ActiveGateway,
        event_type: str,
        device_id: str,
        payload: dict[str, Any],
        severity: str,
    ) -> None:
        device = {**active.entry, "device_id": device_id}
        schedule_event_delivery(
            process_state=self.runtime.process_state,
            event_client=self.event_client,
            auth_context=self.runtime.auth,
            event_type=event_type,
            device=device,
            payload=payload,
            source=INTEGRATION_ID,
            severity=severity,
            record_event=self.record_event,
        )

    @staticmethod
    def sensor_device_id(active: ActiveGateway, sensor: EcowittSensor) -> str:
        return f"{active.entry['device_id']}:{sensor.sensor_id}"
