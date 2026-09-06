from __future__ import annotations

import asyncio

import httpx
import pytest
from piphi_runtime_testkit_python import (
    MockCoreServer,
    assert_entities_response,
    build_config_payload,
    build_runtime_headers,
)

from piphi_network_ecowitt.ecowitt import EcowittSensor, EcowittSnapshot
from piphi_network_ecowitt.main import app
from piphi_network_ecowitt.state import (
    ecowitt_service,
    registry,
    remove_config,
    starter,
    telemetry,
)


async def wait_for(condition, *, timeout: float = 2.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if condition():
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out waiting for Runtime SDK delivery")


class SequencedEcowittClient:
    def __init__(self) -> None:
        self._index = 0

    async def read_snapshot(self) -> EcowittSnapshot:
        wet = self._index > 0
        snapshot = EcowittSnapshot(
            gateway_metrics={
                "connected": True,
                "temperature_c": 22.5,
                "humidity_percent": 58,
                "rain_rate_mmh": 1.2 if wet else 0,
            },
            gateway_units={
                "connected": "bool",
                "temperature_c": "C",
                "humidity_percent": "%",
                "rain_rate_mmh": "mm/h",
            },
            sensors=(
                EcowittSensor(
                    sensor_id="ch_leak-1",
                    name="Basement leak sensor",
                    sensor_type="leak",
                    channel="1",
                    metrics={"connected": True, "leak_detected": wet},
                    units={"connected": "bool", "leak_detected": "bool"},
                ),
                EcowittSensor(
                    sensor_id="lightning-1",
                    name="Lightning sensor",
                    sensor_type="lightning",
                    channel="1",
                    metrics={
                        "connected": True,
                        "lightning_count": 2 if wet else 1,
                        "lightning_distance_km": 8,
                    },
                    units={
                        "connected": "bool",
                        "lightning_count": "count",
                        "lightning_distance_km": "km",
                    },
                ),
            ),
            raw_sections=("ch_leak", "common_list", "lightning"),
        )
        self._index += 1
        return snapshot

    async def close(self) -> None:
        return None


@pytest.mark.anyio
async def test_testkit_captures_telemetry_entities_command_and_transitions(monkeypatch) -> None:
    mock_core = MockCoreServer()
    previous_telemetry_url = telemetry.core_base_url
    previous_event_url = starter.event_client.core_base_url
    monkeypatch.setattr(ecowitt_service, "client_factory", lambda _config: SequencedEcowittClient())
    telemetry.core_base_url = mock_core.base_url
    starter.event_client.core_base_url = mock_core.base_url
    payload = build_config_payload(
        config_id="garden-weather",
        device_id="garden-weather",
        container_id="ecowitt-container",
        integration_id="piphi-network-ecowitt",
        extra={"host": "ecowitt.test", "alias": "Garden weather", "poll_interval_seconds": 3600},
    )
    headers = build_runtime_headers(
        container_id="ecowitt-container", internal_token="fake-runtime-token"
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            configured = await client.post("/config", json=payload, headers=headers)
            assert configured.status_code == 200
            await wait_for(lambda: len(mock_core.telemetry_requests) >= 3)
            gateway_telemetry = mock_core.assert_telemetry_sent(device_id="garden-weather")
            assert gateway_telemetry.json_body["metrics"]["temperature_c"] == 22.5

            entities_response = await client.get("/entities")
            entities = assert_entities_response(entities_response.json())["entities"]
            assert any(entity["device_id"] == "garden-weather:ch_leak-1" for entity in entities)

            refreshed = await client.post(
                "/command",
                headers=headers,
                json={
                    "contract_version": "automation.runtime.command.v1",
                    "command": "refresh",
                    "target": {"config_id": "garden-weather", "device_id": "garden-weather"},
                    "params": {},
                    "capability": "device.refresh",
                    "capability_requirements": ["device.refresh"],
                },
            )
            assert refreshed.status_code == 200
            assert refreshed.json()["connected"] is True
            await wait_for(lambda: len(mock_core.event_requests) >= 3)
            event = mock_core.assert_event_sent(
                device_id="garden-weather:ch_leak-1",
                config_id="garden-weather",
                event_type="sensor.leak_detected",
            )
            normalized_headers = {key.lower(): value for key, value in event.headers.items()}
            assert normalized_headers["x-container-id"] == "ecowitt-container"
            assert normalized_headers["x-piphi-integration-token"] == "fake-runtime-token"
            mock_core.assert_event_sent(
                device_id="garden-weather",
                config_id="garden-weather",
                event_type="weather.rain_started",
            )
            mock_core.assert_event_sent(
                device_id="garden-weather:lightning-1",
                config_id="garden-weather",
                event_type="weather.lightning_detected",
            )
    finally:
        telemetry.core_base_url = previous_telemetry_url
        starter.event_client.core_base_url = previous_event_url
        if registry.get("garden-weather") is not None:
            await remove_config("garden-weather")
        mock_core.shutdown()
