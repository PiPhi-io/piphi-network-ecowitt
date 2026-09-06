# Runtime contract

Integration ID: `piphi-network-ecowitt`.
Deployment: standard integration, local device, port `8090`.

## Lifecycle

PiPhi Core configures a gateway with `POST /config`. Configuration performs one
bounded live-data request before it is accepted, then starts one polling task.
`POST /config/sync` reconciles Core's snapshot and `POST /deconfigure` stops the
task and closes its HTTP client.

The gateway origin is restricted to a bare HTTP(S) origin: embedded credentials,
paths, queries, fragments, redirects, and non-HTTP schemes are rejected.

## Entities and telemetry

`GET /entities` returns a weather-station entity plus deterministic child IDs of
the form `<gateway-device-id>:<section>-<channel>`. Only capabilities actually
reported by a child are attached to that child. Values are normalized to °C,
hPa, m/s, millimeters, kilometers, and the manifest's remaining canonical units.

The Runtime SDK sends authenticated telemetry for the gateway and each child.
The `/state` response contains the latest gateway snapshot and a sanitized child
summary; it never contains credentials because this integration has none.

## Command

The sole command is the idempotent, read-only `refresh` action:

```json
{
  "contract_version": "automation.runtime.command.v1",
  "command": "refresh",
  "target": {
    "config_id": "garden-weather",
    "device_id": "garden-weather"
  },
  "params": {},
  "capability": "device.refresh",
  "capability_requirements": ["device.refresh"]
}
```

## Transition events

Events are emitted only after a baseline reading exists:

- `weather.rain_started` / `weather.rain_stopped`
- `weather.lightning_detected`
- `sensor.leak_detected` / `sensor.leak_cleared`
- `device.offline` / `device.online`

Every event includes stable config/device identity and a minimal payload. Poll
failures are deduplicated until the gateway recovers.

## Widget

`io.piphi.ecowitt.weather-overview` is a read-only Widget SDK package. It uses
the injected host bridge, requests no host/browser permissions, has an empty
connect CSP, and supports light/dark, LTR/RTL, live/stale/offline/error states.
