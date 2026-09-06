from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from piphi_runtime_kit_python import (
    IntegrationDiscoveryRequest,
    build_discovery_response,
    normalize_discovery_inputs,
)

from ..contract import CONFIG_SCHEMA

router = APIRouter(tags=["discovery"])


@router.post("/discover")
async def discover(payload: IntegrationDiscoveryRequest | None = None) -> Any:
    inputs = normalize_discovery_inputs(payload.inputs if payload else None)
    return build_discovery_response(
        [
            {
                "id": "ecowitt-gateway",
                "device_id": "ecowitt-gateway",
                "host": inputs.get("host", "127.0.0.1"),
                "alias": "Ecowitt Weather Gateway",
            }
        ]
    )


@router.get("/ui-config")
async def ui_config() -> dict[str, Any]:
    return CONFIG_SCHEMA
