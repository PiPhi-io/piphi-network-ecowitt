from __future__ import annotations

from piphi_runtime_kit_python import RuntimeConfig
from pydantic import Field, field_validator

from .ecowitt import normalize_base_url


class DeviceConfig(RuntimeConfig):
    host: str
    alias: str | None = None
    poll_interval_seconds: int = Field(default=60, ge=15, le=3600)
    request_timeout_seconds: float = Field(default=5.0, ge=1.0, le=15.0)

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        host = value.strip().rstrip("/")
        if not host:
            raise ValueError("host must not be empty")
        return normalize_base_url(host)
