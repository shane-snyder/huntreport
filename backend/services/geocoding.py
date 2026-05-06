import httpx
import re

_PUBLIC_LAND_RE = re.compile(
    r"\b(forest|wma|wildlife|game lands?|state forest|national forest|management area|preserve|grasslands?|refuge|park)\b",
    re.IGNORECASE,
)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


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
