FROM node:22-slim AS widgets
WORKDIR /widgets/ecowitt-weather-overview
COPY widgets/ecowitt-weather-overview/package*.json ./
RUN npm ci --ignore-scripts
COPY widgets/ecowitt-weather-overview ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=widgets /widgets /app/widgets
ENV PIPHI_WIDGET_DIR=/app/widgets
EXPOSE 8090
CMD ["uvicorn", "piphi_network_ecowitt.main:app", "--host", "0.0.0.0", "--port", "8090"]
