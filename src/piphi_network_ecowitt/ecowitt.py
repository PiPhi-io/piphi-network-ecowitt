from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx


class EcowittError(RuntimeError):
    """A safe, actionable error returned by the Ecowitt transport."""


@dataclass(frozen=True, slots=True)
class EcowittSensor:
    sensor_id: str
    name: str
    sensor_type: str
    channel: str | None
    metrics: dict[str, bool | float | int]
    units: dict[str, str]


@dataclass(frozen=True, slots=True)
class EcowittSnapshot:
    gateway_metrics: dict[str, bool | float | int]
    gateway_units: dict[str, str]
    sensors: tuple[EcowittSensor, ...]
    raw_sections: tuple[str, ...]


class EcowittHttpClient:
    """Small async client for Ecowitt's read-only HTTP LAN endpoints."""

    def __init__(self, host: str, *, timeout_seconds: float = 5.0) -> None:
        self.base_url = normalize_base_url(host)
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout_seconds),
            follow_redirects=False,
        )

    async def read_snapshot(self) -> EcowittSnapshot:
        try:
            response = await self._client.get("/get_livedata_info")
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise EcowittError("Ecowitt gateway timed out") from exc
        except httpx.HTTPStatusError as exc:
            raise EcowittError(f"Ecowitt gateway returned HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise EcowittError("Ecowitt gateway returned an invalid response") from exc
        if not isinstance(payload, dict):
            raise EcowittError("Ecowitt live-data response must be a JSON object")
        return normalize_livedata(payload)

    async def close(self) -> None:
        await self._client.aclose()


def normalize_base_url(host: str) -> str:
    candidate = host.strip().rstrip("/")
    if "://" not in candidate:
        candidate = f"http://{candidate}"
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("host must be an HTTP(S) Ecowitt gateway address")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("host must not contain credentials, query, or fragment")
    if parsed.path not in {"", "/"}:
        raise ValueError("host must not contain a path")
    return candidate


COMMON_FIELDS: dict[str, tuple[str, str]] = {
    "0x01": ("indoor_temperature_c", "C"),
    "0x02": ("temperature_c", "C"),
    "0x03": ("dew_point_c", "C"),
    "0x04": ("wind_chill_c", "C"),
    "0x05": ("heat_index_c", "C"),
    "0x06": ("indoor_humidity_percent", "%"),
    "0x07": ("humidity_percent", "%"),
    "0x08": ("absolute_pressure_hpa", "hPa"),
    "0x09": ("pressure_hpa", "hPa"),
    "0x0a": ("wind_direction_deg", "deg"),
    "0x0b": ("wind_speed_ms", "m/s"),
    "0x0c": ("wind_gust_ms", "m/s"),
    "0x0d": ("rain_event_mm", "mm"),
    "0x0e": ("rain_rate_mmh", "mm/h"),
    "0x10": ("rain_daily_mm", "mm"),
    "0x11": ("rain_weekly_mm", "mm"),
    "0x12": ("rain_monthly_mm", "mm"),
    "0x13": ("rain_yearly_mm", "mm"),
    "0x14": ("rain_total_mm", "mm"),
    "0x15": ("solar_irradiance_wm2", "W/m2"),
    "0x17": ("uv_index", "index"),
    "0x19": ("daily_max_wind_ms", "m/s"),
}


def normalize_livedata(payload: dict[str, Any]) -> EcowittSnapshot:
    gateway_metrics: dict[str, bool | float | int] = {"connected": True}
    gateway_units: dict[str, str] = {"connected": "bool"}
    common = payload.get("common_list")
    if isinstance(common, list):
        for item in common:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).lower()
            field = COMMON_FIELDS.get(item_id)
            if field is None:
                continue
            metric, target_unit = field
            parsed = parse_measurement(item.get("val"), str(item.get("unit") or ""), target_unit)
            if parsed is not None:
                gateway_metrics[metric] = parsed
                gateway_units[metric] = target_unit

    for section in ("rain", "piezoRain"):
        values = payload.get(section)
        if not isinstance(values, list):
            continue
        prefix = "piezo_" if section == "piezoRain" else ""
        for item in values:
            if not isinstance(item, dict):
                continue
            item_id = str(item.get("id", "")).lower()
            field = COMMON_FIELDS.get(item_id)
            if field and field[0].startswith("rain_"):
                metric = f"{prefix}{field[0]}"
                parsed = parse_measurement(item.get("val"), str(item.get("unit") or ""), field[1])
                if parsed is not None:
                    gateway_metrics[metric] = parsed
                    gateway_units[metric] = field[1]

    sensors: list[EcowittSensor] = []
    sensors.extend(_channel_sensors(payload, "ch_aisle", "temperature_humidity"))
    sensors.extend(_channel_sensors(payload, "ch_temp", "temperature"))
    sensors.extend(_channel_sensors(payload, "ch_soil", "soil"))
    sensors.extend(_channel_sensors(payload, "ch_leaf", "leaf"))
    sensors.extend(_channel_sensors(payload, "ch_leak", "leak"))
    sensors.extend(_channel_sensors(payload, "ch_pm25", "pm25"))
    sensors.extend(_channel_sensors(payload, "ch_lds", "level"))
    sensors.extend(_single_sensors(payload, "lightning", "lightning"))
    sensors.extend(_single_sensors(payload, "co2", "air_quality"))
    sensors.extend(_single_sensors(payload, "wh25", "indoor_climate"))
    return EcowittSnapshot(
        gateway_metrics=gateway_metrics,
        gateway_units=gateway_units,
        sensors=tuple(sensors),
        raw_sections=tuple(sorted(str(key) for key in payload)),
    )


def _channel_sensors(
    payload: dict[str, Any], section: str, sensor_type: str
) -> list[EcowittSensor]:
    values = payload.get(section)
    if not isinstance(values, list):
        return []
    result: list[EcowittSensor] = []
    for index, item in enumerate(values, start=1):
        if not isinstance(item, dict):
            continue
        channel = str(item.get("channel") or index)
        result.append(_sensor(section, sensor_type, channel, item))
    return result


def _single_sensors(payload: dict[str, Any], section: str, sensor_type: str) -> list[EcowittSensor]:
    values = payload.get(section)
    if not isinstance(values, list):
        return []
    return [
        _sensor(section, sensor_type, str(index), item)
        for index, item in enumerate(values, start=1)
        if isinstance(item, dict)
    ]


def _sensor(section: str, sensor_type: str, channel: str, item: dict[str, Any]) -> EcowittSensor:
    metrics: dict[str, bool | float | int] = {"connected": True}
    units: dict[str, str] = {"connected": "bool"}
    field_specs = {
        "temp": ("temperature_c", "C"),
        "humidity": ("humidity_percent", "%"),
        "PM25": ("pm25_ugm3", "ug/m3"),
        "PM10": ("pm10_ugm3", "ug/m3"),
        "PM1": ("pm1_ugm3", "ug/m3"),
        "PM4": ("pm4_ugm3", "ug/m3"),
        "CO2": ("co2_ppm", "ppm"),
        "battery": ("battery_level", "level"),
        "voltage": ("battery_voltage_v", "V"),
        "depth": ("depth_mm", "mm"),
        "air": ("air_gap_mm", "mm"),
    }
    for source, (target, unit) in field_specs.items():
        if source not in item:
            continue
        if source == "humidity" and sensor_type == "soil":
            target = "soil_moisture_percent"
        elif source == "humidity" and sensor_type == "leaf":
            target = "leaf_wetness_percent"
        source_unit = str(item.get("unit") or "") if source == "temp" else ""
        parsed = parse_measurement(item[source], source_unit, unit)
        if parsed is not None:
            metrics[target] = parsed
            units[target] = unit
    if "status" in item:
        status = str(item["status"]).strip().lower()
        metrics["leak_detected"] = status not in {"normal", "ok", "dry", "0", "false"}
        units["leak_detected"] = "bool"
    if sensor_type == "lightning":
        distance = parse_measurement(item.get("distance"), "", "km")
        count = parse_measurement(item.get("count"), "", "count")
        if distance is not None:
            metrics["lightning_distance_km"] = distance
            units["lightning_distance_km"] = "km"
        if count is not None:
            metrics["lightning_count"] = count
            units["lightning_count"] = "count"
    name = str(item.get("name") or f"{sensor_type.replace('_', ' ').title()} {channel}")
    return EcowittSensor(
        sensor_id=f"{section}-{_slug(channel)}",
        name=name,
        sensor_type=sensor_type,
        channel=channel,
        metrics=metrics,
        units=units,
    )


NUMBER = re.compile(r"[-+]?\d+(?:\.\d+)?")


def parse_measurement(value: Any, source_unit: str, target_unit: str) -> float | int | None:
    if value is None or isinstance(value, bool):
        return None
    match = NUMBER.search(str(value).replace(",", ""))
    if match is None:
        return None
    number = float(match.group())
    combined_unit = f"{source_unit} {value}".lower()
    if target_unit == "C" and "f" in combined_unit and "°c" not in combined_unit:
        number = (number - 32.0) * 5.0 / 9.0
    elif target_unit == "hPa" and "inhg" in combined_unit:
        number *= 33.8638866667
    elif target_unit == "m/s":
        if "mph" in combined_unit:
            number *= 0.44704
        elif "km/h" in combined_unit or "kph" in combined_unit:
            number /= 3.6
        elif "knot" in combined_unit:
            number *= 0.514444
    elif target_unit in {"mm", "mm/h"} and " in" in f" {combined_unit}":
        number *= 25.4
    elif target_unit == "km" and " mi" in f" {combined_unit}":
        number *= 1.609344
    rounded = round(number, 3)
    return int(rounded) if rounded.is_integer() else rounded


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "1"
