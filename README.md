# PiPhi Network Ecowitt

Cloud-free PiPhi integration for Ecowitt weather gateways and their attached
sensors. It polls the gateway's official HTTP LAN API and projects normalized
weather-station and child-sensor entities, telemetry, transition events, and a
sandboxed dashboard widget.

## Supported data

- Outdoor and indoor temperature/humidity, dew point, heat index, and wind chill
- Relative/absolute pressure, wind direction/speed/gust, solar irradiance, and UV
- Traditional and piezo rain rates/totals
- Multi-channel temperature/humidity, temperature, soil moisture, leaf wetness,
  leak, PM2.5, level/depth, lightning, and CO2/particulate sensors
- Battery level/voltage fields reported by the gateway

The integration intentionally does not expose the protocol's network,
calibration, firmware, reboot, reset, or actuator-writing endpoints.

## Device requirements

Use an Ecowitt gateway or console with the HTTP LAN API. Ecowitt's current
generic protocol documents `GET /get_livedata_info`; older TCP-only devices may
not support this integration. Give the gateway a DHCP reservation so its address
does not change.

In PiPhi, add the integration and enter:

- `host`: gateway IP or HTTP(S) origin, for example `192.168.1.50`
- `alias`: optional display name
- `poll_interval_seconds`: 15–3600 seconds (default 60)
- `request_timeout_seconds`: 1–15 seconds (default 5)

No Ecowitt cloud account or API key is required. The PiPhi runtime container
must be able to reach the gateway on the local network.

## Development

```bash
pdm install -G dev
pdm run pytest
pdm run ruff check .
pdm run mypy src
pdm run python scripts/validate.py
node ../PiPhi/piphi_network_create/dist/index.js validate -C .
```

Widget gates:

```bash
cd widgets/ecowitt-weather-overview
npm ci
npm run validate
npm test
npm run build
npm run conformance
```

Run locally with `pdm run uvicorn piphi_network_ecowitt.main:app --port 8090`.
See [docs/contract.md](docs/contract.md) for the runtime and automation contract.

## Container

```bash
docker build -t docker.io/piphinetwork/piphi-network-ecowitt:0.1.1 .
docker run --rm -p 8090:8090 docker.io/piphinetwork/piphi-network-ecowitt:0.1.1
```

The image contains the prebuilt Widget SDK bundle under `/app/widgets` and sets
`PIPHI_WIDGET_DIR` for PiPhi Core's widget asset gateway.

## License

Apache-2.0
