import { getInjectedPiPhiWidgetHost } from "piphi-network-widget-sdk";

const host = getInjectedPiPhiWidgetHost();
const root = document.querySelector("#piphi-widget-root") || document.body;
const context = await host.getContext();
const title = await host.translate("widget.title");
const direction = context.localization?.direction || "ltr";

root.innerHTML = `
  <style>
    :root { color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }
    * { box-sizing: border-box; }
    body { margin: 0; }
    main { min-height: 220px; padding: 20px; border-radius: 20px; color: #102a43; background: linear-gradient(145deg, #f7fbff, #e7f4ff); }
    [data-theme="dark"] main { color: #edf8ff; background: linear-gradient(145deg, #102a43, #173f5f); }
    header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
    h1 { margin: 0; font-size: 1rem; letter-spacing: .02em; }
    [role="status"] { font-size: .78rem; opacity: .75; }
    .hero { display: flex; align-items: end; gap: 14px; margin: 20px 0; }
    .temperature { font-size: clamp(2.8rem, 13vw, 4.8rem); font-weight: 750; line-height: .85; }
    .condition { display: grid; gap: 5px; padding-bottom: 3px; }
    .condition strong { font-size: 1.05rem; }
    .grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 9px; }
    .metric { min-width: 0; padding: 10px; border: 1px solid rgb(82 145 184 / 22%); border-radius: 12px; background: rgb(255 255 255 / 52%); }
    [data-theme="dark"] .metric { background: rgb(255 255 255 / 7%); }
    .metric span { display: block; overflow: hidden; font-size: .69rem; opacity: .7; text-overflow: ellipsis; white-space: nowrap; }
    .metric output { display: block; margin-top: 3px; font-size: 1rem; font-weight: 650; }
    .offline { filter: grayscale(1); opacity: .7; }
    @media (max-width: 400px) { .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
  </style>
  <main dir="${direction}" aria-labelledby="widget-title">
    <header><h1 id="widget-title"></h1><span role="status" aria-live="polite">loading</span></header>
    <section class="hero" aria-label="Current outdoor conditions">
      <output class="temperature" aria-label="Temperature">—</output>
      <div class="condition"><strong class="humidity">—</strong><span class="summary">Waiting for readings</span></div>
    </section>
    <section class="grid" aria-label="Weather details"></section>
  </main>`;

root.querySelector("#widget-title").textContent = title;
const main = root.querySelector("main");
const status = root.querySelector('[role="status"]');
const temperature = root.querySelector(".temperature");
const humidity = root.querySelector(".humidity");
const summary = root.querySelector(".summary");
const grid = root.querySelector(".grid");

const metricDefinitions = [
  ["wind_speed_ms", "Wind", "m/s"], ["wind_gust_ms", "Gust", "m/s"],
  ["rain_rate_mmh", "Rain rate", "mm/h"], ["rain_daily_mm", "Rain today", "mm"],
  ["pressure_hpa", "Pressure", "hPa"], ["uv_index", "UV index", ""],
  ["solar_irradiance_wm2", "Solar", "W/m²"], ["dew_point_c", "Dew point", "°C"],
  ["lightning_distance_km", "Lightning", "km"], ["soil_moisture_percent", "Soil", "%"],
  ["pm25_ugm3", "PM2.5", "µg/m³"], ["co2_ppm", "CO₂", "ppm"],
];

function stateFrom(event) {
  const data = event?.data?.primaryState ?? event?.data?.state ?? event?.data?.value ?? event?.data ?? {};
  if (data && typeof data === "object" && !Array.isArray(data)) return data.metrics ?? data;
  return {};
}

function format(value, unit, digits = 1) {
  if (value === undefined || value === null || value === "") return "—";
  const number = Number(value);
  const shown = Number.isFinite(number) ? number.toLocaleString(undefined, { maximumFractionDigits: digits }) : String(value);
  return unit ? `${shown} ${unit}` : shown;
}

function render(state, connectionStatus) {
  const connected = state.connected !== false && connectionStatus !== "offline";
  main.classList.toggle("offline", !connected);
  status.textContent = connected ? (connectionStatus || "live") : "offline";
  temperature.textContent = format(state.temperature_c ?? state.indoor_temperature_c, "°C");
  humidity.textContent = format(state.humidity_percent ?? state.indoor_humidity_percent, "%", 0);
  const rain = Number(state.rain_rate_mmh ?? 0);
  const wind = Number(state.wind_speed_ms ?? 0);
  summary.textContent = rain > 0 ? "Rain detected" : wind > 10 ? "Windy" : connected ? "Live Ecowitt data" : "Gateway unavailable";
  grid.replaceChildren();
  for (const [key, label, unit] of metricDefinitions) {
    if (state[key] === undefined || state[key] === null) continue;
    const card = document.createElement("div");
    card.className = "metric";
    const caption = document.createElement("span");
    caption.textContent = label;
    const output = document.createElement("output");
    output.textContent = format(state[key], unit);
    card.append(caption, output);
    grid.append(card);
  }
}

const stop = await host.subscribeState({}, (event) => {
  if (event.kind === "status") {
    render({}, event.status);
    return;
  }
  if (event.kind === "error") {
    status.textContent = "error";
    return;
  }
  if (event.kind === "snapshot" || event.kind === "point") render(stateFrom(event), event.status);
});

window.addEventListener("pagehide", stop, { once: true });
await host.ready({ height: 300 });
