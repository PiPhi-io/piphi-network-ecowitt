from __future__ import annotations

import json
from pathlib import Path

from piphi_network_ecowitt.contract import CAPABILITIES, COMMANDS, REQUIRED_ENDPOINTS
from piphi_network_ecowitt.main import app


def test_runtime_implements_contract_routes() -> None:
    routes = set(app.openapi()["paths"])
    for path in [
        "/health",
        "/diagnostics",
        "/discover",
        "/config",
        "/config/sync",
        "/deconfigure",
        "/deconfigure/{config_id}",
        "/ui-config",
        "/entities",
        "/state",
        "/contract",
        "/events",
        "/events/device/{config_id}/example",
        "/telemetry/example",
        "/telemetry/device/{config_id}/example",
        "/command",
    ]:
        assert path in routes

    assert REQUIRED_ENDPOINTS == ["health", "entities", "command", "config", "ui_config"]
    assert "refresh" in COMMANDS


def test_manifest_behaviors_and_runtime_registrations_agree() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads((root / "manifest.json").read_text())
    behaviors = json.loads((root / "src" / "behaviors.json").read_text())
    assert manifest["version"] == "0.1.1"
    assert manifest["commands"] == COMMANDS
    assert set(manifest["capabilities"]) == set(CAPABILITIES)
    assert manifest["ui"]["widget_packages"][0]["id"] == "io.piphi.ecowitt.weather-overview"
    widget = root / "widgets" / "ecowitt-weather-overview"
    widget_package = json.loads((widget / "package.json").read_text())
    widget_manifest = json.loads((widget / "widget.manifest.json").read_text())
    assert {manifest["version"], widget_package["version"], widget_manifest["version"]} == {"0.1.1"}
    assert manifest["ui"]["widget_packages"][0]["version"] == manifest["version"]
    action_ids = {action["id"] for device in behaviors["devices"] for action in device["actions"]}
    assert action_ids == set(COMMANDS)
