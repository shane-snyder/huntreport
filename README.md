# HuntReport

A hunting report web application built with FastAPI. Given a location, it provides weather forecasts, wind & moon intelligence, game activity predictions, and nearby public hunting lands.

Inspired by [CastReport](https://github.com/dbahret/CastReport) — same architecture, retargeted from rod and reel to bow and rifle.

## Features

- **Hunt Index (0–100)** — composite score from temperature, wind, barometer, moon phase, cloud cover, and precipitation
- **Game activity per species** — region-aware list (whitetail, mule deer, elk, turkey, pheasant, hogs, bear, etc.) tagged HOT / ACTIVE / FAIR / SLOW with rut flags and species-specific tactics
- **Wind & moon panel** — compass rose, gust speed, illumination, hunt-impact rating
- **Best times** — sunrise/sunset-driven dawn/morning/midday/evening/night windows
- **Public hunting lands** — live OSM Overpass discovery of nearby state/national forests, WMAs, and refuges, with curated fallback for the major U.S. regions
- **7-day day-picker** — re-score any day in the upcoming week

## Prerequisites

- **Python 3.12+** — `brew install python@3.12`
- **Podman** (optional, for containerized runs) — `brew install podman` then `podman machine init && podman machine start`

## Local Development

### Run without a container

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8080 --reload
```

Open [http://localhost:8080](http://localhost:8080).

### Run with Podman

```bash
podman build -t huntreport .
podman run -d --name huntreport -p 8080:8080 huntreport
```

Stop and remove:

```bash
podman stop huntreport && podman rm huntreport
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/health` | Liveness probe |
| `GET /api/geocode?q=...` | Resolve location string to lat/lon |
| `GET /api/weather?lat=..&lon=..` | Current + 7-day forecast |
| `GET /api/terrain?lat=..&lon=..` | Elevation + terrain zone |
| `GET /api/report?lat=..&lon=..&name=..&day_index=0` | Full hunt report |

## Data sources

- [Open-Meteo](https://open-meteo.com/) — weather forecast (no API key)
- [Nominatim](https://nominatim.openstreetmap.org/) — geocoding
- [Overpass API](https://overpass-api.de/) — public-land discovery
- [USGS EPQS](https://epqs.nationalmap.gov/) — point elevation (US)

All sources are free and require no API key. Be a good citizen — the user-agent header is set per their usage policies.

## Deployment (sno-mini via sno hub ArgoCD)

HuntReport runs on the **sno-mini** spoke and is managed by the agent-based ArgoCD on the **sno** hub.

```bash
# Push this repo to GitHub first (shane-snyder/huntreport on the main branch).

# 1. Populate Vault paths on sno-mini (one-time):
#    huntreport/quay-push-secret           → property .dockerconfigjson
#    openshift-gitops/repo-huntreport      → property password (GitHub PAT)

# 2. Register the Application on the sno hub:
oc login -u kubeadmin -p "$(cat ~/Documents/SNO/kubeadmin)" \
  --server=https://api.sno.shanehomelab.com:6443
oc apply -f bootstrap/argocd-application.yaml

# 3. Watch the sync (status is mirrored on the hub):
oc -n argocd-agent-sno-mini get application huntreport -w
```

Once `Synced` and `Healthy`, the app is reachable at:

```
https://huntreport-huntreport.apps.sno-mini.shanehomelab.com
```

See [bootstrap/README.md](./bootstrap/README.md) for details.

## CI/CD

Two Tekton pipelines run on sno-mini in the `huntreport` namespace:

| Branch | Pipeline | Image tag |
|---|---|---|
| `main` | `huntreport-prod` | `:latest` + `:prod-N` (sequential) |
| any other | `huntreport-dev` | `:dev-<branch>` with branch-specific Deployment / Service / Route |

A `huntreport-poll` CronJob runs every 2 minutes, polls the GitHub API, and triggers the right pipeline on new commits. When a non-main branch is deleted on GitHub, the corresponding dev resources are automatically reaped.

## Disclaimer

HuntReport is an aid, not authority. Always verify open seasons, license requirements, unit-specific rules, and access boundaries with the managing state or federal agency before hunting.
