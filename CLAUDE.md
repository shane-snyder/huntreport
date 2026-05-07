# HuntReport

Hunting report web app — enter a location and get weather, wind/moon analysis, game activity predictions, and nearby public hunting lands. Built with Python 3.12 / FastAPI / Uvicorn, served on port 8080. Frontend is a single-page static HTML file served by FastAPI.

## Common Commands

```bash
# Build and run locally with Podman
podman build -t huntreport .
podman stop huntreport 2>/dev/null; podman rm huntreport 2>/dev/null
podman run -d --name huntreport -p 8080:8080 huntreport
curl -sf http://localhost:8080/api/health

# Run without a container
cd backend && pip install -r requirements.txt && uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

## Architecture

```
backend/
├── main.py              # FastAPI app, routes, static mount
├── requirements.txt     # fastapi, uvicorn[standard], httpx
├── services/            # Each module = one data source
│   ├── geocoding.py     # Location → lat/lon (Nominatim + local cache)
│   ├── weather.py       # Open-Meteo current + 7-day forecast
│   ├── terrain.py       # USGS / Open-Meteo elevation → zone classification
│   ├── hunting.py       # Hunt score, game activity, best times, moon
│   └── spots.py         # Public-land discovery (Overpass + curated regions)
└── static/index.html    # Full frontend SPA
Dockerfile               # python:3.12-slim, runs as UID 1001
```

## Data sources

- **Open-Meteo** — temperature, wind, pressure, humidity, sunrise/sunset, 7-day forecast
- **OpenStreetMap Nominatim** — geocoding ("Bridger-Teton" → lat/lon)
- **OpenStreetMap Overpass** — protected areas, national/state forests, WMAs
- **USGS EPQS** — point elevation (US only) with Open-Meteo fallback worldwide

## Scoring model

The hunt index (0–100) combines:

- **Time of day** — dawn/dusk weighted heavily, midday penalized
- **Air temperature** — cool windows (25–50°F) score best for big game
- **Wind** — 3–10 mph ideal, dead calm penalized (thermals dominate), >20 mph penalized hard
- **Barometric pressure** — high & stable = active animals
- **Cloud cover** — partial overcast extends low-light feeding
- **Precipitation** — light rain neutral, downpour penalized
- **Moon illumination** — full moon penalty (more nocturnal feeding)

Per-species activity additionally factors in season membership, rut months,
and species-specific temperature window.

## Change Checklist

| If you change... | Also update... |
|---|---|
| Python dependency | `backend/requirements.txt` |
| Listening port | `Dockerfile` EXPOSE |
| Health endpoint path | any container probes |
| System-level dependency | `Dockerfile` — add `RUN apt-get install` |
| Python version | `Dockerfile` FROM line |
