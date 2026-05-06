import logging

from fastapi import FastAPI, Query, HTTPException
from fastapi.staticfiles import StaticFiles
from pathlib import Path

from services.geocoding import geocode_location
from services.weather import fetch_weather
from services.terrain import fetch_terrain_data
from services.hunting import build_hunting_analysis
from services.spots import discover_spots

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("huntreport")

app = FastAPI(title="HuntReport API")

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/geocode")
async def geocode(q: str = Query(..., min_length=1)):
    try:
        return await geocode_location(q)
    except Exception as exc:
        log.exception("Geocode failed for q=%s", q)
        raise HTTPException(status_code=502, detail=str(exc))


@app.get("/api/weather")
async def weather(lat: float = Query(...), lon: float = Query(...)):
    return await fetch_weather(lat, lon)


@app.get("/api/terrain")
async def terrain(lat: float = Query(...), lon: float = Query(...)):
    return await fetch_terrain_data(lat, lon)


@app.get("/api/report")
async def report(
    lat: float = Query(...),
    lon: float = Query(...),
    name: str = Query(""),
    day_index: int = Query(0, ge=0, le=6),
):
    log.info("Report request: lat=%.4f lon=%.4f name=%s day=%d", lat, lon, name, day_index)

    wx = await fetch_weather(lat, lon)
    terrain_data = await fetch_terrain_data(lat, lon)
    analysis = build_hunting_analysis(lat, lon, name, wx, terrain_data, day_index)
    spots = await discover_spots(lat, lon, name)

    return {
        "weather":  wx,
        "terrain":  terrain_data,
        "analysis": analysis,
        "spots":    spots,
        "ai": {
            "score":       analysis["score"],
            "verdict":     analysis["verdict"],
            "insight":     analysis["insight"],
            "game":        analysis["game"],
            "hourly":      analysis["hourly"],
            "bestWindows": analysis["bestWindows"],
            "sunriseHour": analysis["sunriseHour"],
            "sunsetHour":  analysis["sunsetHour"],
            "moon":        analysis["moon"],
            "wind":        analysis["wind"],
            "publicLands": spots,
        },
    }


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
