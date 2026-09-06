from __future__ import annotations

import pytest

from piphi_network_ecowitt.ecowitt import normalize_base_url, normalize_livedata


def test_normalizes_gateway_and_accessory_channels() -> None:
    snapshot = normalize_livedata(
        {
            "common_list": [
                {"id": "0x02", "val": "68.0", "unit": "F"},
                {"id": "0x07", "val": "54%"},
                {"id": "0x0B", "val": "10.0 mph"},
                {"id": "0x09", "val": "29.92 inHg"},
                {"id": "0x0E", "val": "0.20 in/Hr"},
            ],
            "ch_aisle": [
                {
                    "channel": "2",
                    "name": "Greenhouse",
                    "temp": "77 F",
                    "humidity": "61%",
                    "battery": "4",
                }
            ],
            "ch_soil": [{"channel": "1", "name": "Tomatoes", "humidity": "38%", "battery": "5"}],
            "ch_leak": [{"channel": "1", "name": "Basement", "status": "Leak", "battery": "2"}],
            "lightning": [{"distance": "12 mi", "count": "3", "battery": "4"}],
        }
    )
    assert snapshot.gateway_metrics["temperature_c"] == 20
    assert snapshot.gateway_metrics["wind_speed_ms"] == 4.47
    assert snapshot.gateway_metrics["pressure_hpa"] == 1013.207
    assert snapshot.gateway_metrics["rain_rate_mmh"] == 5.08
    greenhouse = next(sensor for sensor in snapshot.sensors if sensor.name == "Greenhouse")
    assert greenhouse.metrics["temperature_c"] == 25
    soil = next(sensor for sensor in snapshot.sensors if sensor.sensor_type == "soil")
    assert soil.metrics["soil_moisture_percent"] == 38
    leak = next(sensor for sensor in snapshot.sensors if sensor.sensor_type == "leak")
    assert leak.metrics["leak_detected"] is True
    lightning = next(sensor for sensor in snapshot.sensors if sensor.sensor_type == "lightning")
    assert lightning.metrics["lightning_distance_km"] == 19.312


@pytest.mark.parametrize(
    "value",
    [
        "ftp://weather.local",
        "http://user:pass@weather.local",
        "http://weather.local/path",
        "http://weather.local?q=1",
    ],
)
def test_rejects_unsafe_gateway_origins(value: str) -> None:
    with pytest.raises(ValueError):
        normalize_base_url(value)


def test_accepts_bare_host_and_http_origins() -> None:
    assert normalize_base_url("192.168.1.50") == "http://192.168.1.50"
    assert normalize_base_url("https://weather.local/") == "https://weather.local"
