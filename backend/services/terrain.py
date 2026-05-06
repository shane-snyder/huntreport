"""
Terrain / elevation lookup for hunting context.

Uses USGS Elevation Point Query Service for the lookup point and
Open-Meteo Elevation API as a fallback. Terrain elevation drives
zone classification (lowland / foothills / montane / alpine), which
in turn affects which game species are likely.
"""

import httpx

USGS_EPQS_URL = "https://epqs.nationalmap.gov/v1/json"
OPEN_METEO_ELEV_URL = "https://api.open-meteo.com/v1/elevation"


async def fetch_terrain_data(lat: float, lon: float) -> dict:
    """Fetch elevation and derive terrain zone classification."""
    elevation = await _fetch_elevation(lat, lon)

    if elevation is None:
        zone = "UNKNOWN"
        zone_desc = ""
    elif elevation < 800:
        zone = "LOWLAND"
        zone_desc = "Bottomlands, swamp edges, ag fields, river hardwoods."
    elif elevation < 2000:
        zone = "FOOTHILLS"
        zone_desc = "Mixed hardwoods, ridge benches, oak flats."
    elif elevation < 5000:
        zone = "MONTANE"
        zone_desc = "Steep timber, conifer-aspen mix, drainages."
    elif elevation < 9000:
        zone = "SUBALPINE"
        zone_desc = "High dark timber, basins, transition belts."
    else:
        zone = "ALPINE"
        zone_desc = "Above timber — tundra, scree, headwall basins."

    return {
        "elevationFt": elevation,
        "zone":        zone,
        "zoneDesc":    zone_desc,
    }


async def _fetch_elevation(lat: float, lon: float) -> float | None:
    async with httpx.AsyncClient(timeout=10) as client:
        # USGS EPQS — only covers the US, returns meters
        try:
            resp = await client.get(USGS_EPQS_URL, params={
                "x": lon,
                "y": lat,
                "units": "Feet",
                "wkid": 4326,
                "includeDate": "false",
            })
            if resp.is_success:
                data = resp.json()
                val = data.get("value")
                if val is not None:
                    v = float(val)
                    if v > -1000:
                        return round(v, 0)
        except (httpx.HTTPError, ValueError, KeyError, TypeError):
            pass

        # Open-Meteo elevation fallback — global, returns meters
        try:
            resp = await client.get(OPEN_METEO_ELEV_URL, params={
                "latitude": lat,
                "longitude": lon,
            })
            if resp.is_success:
                data = resp.json()
                elev_list = data.get("elevation") or []
                if elev_list:
                    meters = float(elev_list[0])
                    return round(meters * 3.28084, 0)
        except (httpx.HTTPError, ValueError, KeyError, TypeError, IndexError):
            pass

    return None
