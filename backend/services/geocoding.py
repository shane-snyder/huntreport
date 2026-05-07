import httpx
import re

_PUBLIC_LAND_RE = re.compile(
    r"\b(forest|wma|wildlife|game lands?|state forest|national forest|management area|preserve|grasslands?|refuge|park)\b",
    re.IGNORECASE,
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"


async def reverse_geocode(lat: float, lon: float) -> dict:
    """Resolve coordinates to a friendly place name via Nominatim reverse."""
    headers = {"User-Agent": "HuntReport/1.0 (hunting-app)"}
    params = {"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1, "zoom": 10}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(NOMINATIM_REVERSE_URL, params=params, headers=headers)
            if not resp.is_success:
                return {"lat": lat, "lon": lon, "name": _fallback_label(lat, lon), "type": "unknown"}
            r = resp.json()
    except (httpx.HTTPError, ValueError):
        return {"lat": lat, "lon": lon, "name": _fallback_label(lat, lon), "type": "unknown"}

    addr = r.get("address", {}) or {}
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or addr.get("county", "")
    state = addr.get("state", "")
    state_code = (addr.get("ISO3166-2-lvl4") or "").split("-")[-1] or state
    if city and state_code:
        name = f"{city}, {state_code}"
    elif city and state:
        name = f"{city}, {state}"
    else:
        display = r.get("display_name", "")
        name = display.split(",")[0] if display else _fallback_label(lat, lon)
    return {"lat": lat, "lon": lon, "name": name, "displayName": r.get("display_name", ""), "type": "city"}


def _fallback_label(lat: float, lon: float) -> str:
    return f"{lat:.3f}°N, {abs(lon):.3f}°{'W' if lon < 0 else 'E'}"


async def geocode_location(query: str) -> dict:
    """Resolve a location string to coordinates via Nominatim."""
    q = query.strip()
    is_public_land = bool(_PUBLIC_LAND_RE.search(q))

    params = {
        "q": q,
        "format": "jsonv2",
        "limit": 5,
        "addressdetails": 1,
    }
    headers = {"User-Agent": "HuntReport/1.0 (hunting-app)"}

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(NOMINATIM_URL, params=params, headers=headers)
        resp.raise_for_status()
        results = resp.json()

    if not results:
        return {"error": f"Could not find '{q}'", "lat": None, "lon": None, "name": q, "type": "unknown"}

    if is_public_land:
        land_classes = {"boundary", "leisure", "natural", "landuse"}
        for r in results:
            if r.get("category") in land_classes or r.get("class") in land_classes:
                return _format_result(r, is_public_land=True)

    best = results[0]
    return _format_result(best, is_public_land=is_public_land)


def _format_result(result: dict, is_public_land: bool = False) -> dict:
    addr = result.get("address", {})
    city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("county", "")
    state = addr.get("state", "")

    land_types = {"boundary", "leisure", "natural", "landuse"}
    loc_type = "land" if (is_public_land or result.get("category") in land_types) else "city"

    display = result.get("display_name", "")
    name = result.get("name", "")
    if city and state:
        near_city = f"{city}, {state}"
    else:
        near_city = display.split(",")[0] if display else name

    return {
        "lat": float(result["lat"]),
        "lon": float(result["lon"]),
        "name": name or near_city,
        "displayName": display,
        "nearCity": near_city,
        "type": loc_type,
    }
