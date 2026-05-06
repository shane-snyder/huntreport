"""
Public hunting lands discovery.

Queries OpenStreetMap Overpass for nearby protected areas (state forests,
national forests, wildlife management areas, game lands), then falls back
to curated regional data when the live query fails or is sparse.
"""

import httpx
import re
from math import radians, cos, sin, asin, sqrt

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 3956 * 2 * asin(sqrt(a))


def _classify_land(name: str, tags: dict) -> str:
    n = (name or "").lower()
    designation = (tags.get("boundary") or "") + " " + (tags.get("protect_class") or "") + " " + (tags.get("leisure") or "") + " " + (tags.get("landuse") or "")
    designation = designation.lower()
    if re.search(r"\b(wma|wildlife management|game land|game preserve|hunt(ing)?)\b", n):
        return "wma"
    if re.search(r"\b(national forest|state forest|forest)\b", n) or "forest" in designation:
        return "forest"
    if re.search(r"\b(refuge|preserve|conservation|sanctuary)\b", n):
        return "refuge"
    return "public"


_REGION_BOXES: list[tuple[str, float, float, float, float]] = [
    ("northeast_appalachian",   36.5, -82.5, 47.5, -69.5),
    ("southeast",               24.5, -92.0, 36.5, -75.0),
    ("midwest_farmbelt",        36.5, -97.5, 43.5, -82.5),
    ("great_lakes_northwoods",  43.5, -97.5, 49.5, -82.5),
    ("great_plains",            33.0, -106.0, 49.0, -97.5),
    ("rocky_mountains",         33.0, -117.0, 49.5, -104.0),
    ("pacific_northwest",       42.0, -125.0, 49.5, -116.0),
    ("california",              32.5, -125.0, 42.0, -114.0),
    ("southwest_desert",        28.0, -114.0, 36.5, -103.0),
    ("alaska",                  53.0, -170.0, 71.5, -130.0),
]


def _lat_lon_to_region(lat: float, lon: float) -> str | None:
    for region_id, s_lat, w_lon, n_lat, e_lon in _REGION_BOXES:
        if s_lat <= lat <= n_lat and w_lon <= lon <= e_lon:
            return region_id
    return None


# ── Overpass discovery ──────────────────────────────────────────────────

async def _discover_overpass(lat: float, lon: float) -> list[dict]:
    """Query OpenStreetMap Overpass for nearby protected/managed land."""
    delta = 0.6  # ~40 mi window
    south, west = lat - delta, lon - delta
    north, east = lat + delta, lon + delta
    query = f"""
    [out:json][timeout:25];
    (
      relation["boundary"="protected_area"]({south},{west},{north},{east});
      relation["boundary"="national_park"]({south},{west},{north},{east});
      relation["leisure"="nature_reserve"]({south},{west},{north},{east});
      way["leisure"="nature_reserve"]({south},{west},{north},{east});
      relation["landuse"="forest"]["name"]({south},{west},{north},{east});
      way["landuse"="forest"]["name"]({south},{west},{north},{east});
    );
    out center tags 60;
    """

    for url in OVERPASS_URLS:
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(url, data={"data": query}, headers={"User-Agent": "HuntReport/1.0"})
                if not resp.is_success:
                    continue
                data = resp.json()
                elements = data.get("elements", [])
                if elements:
                    return _format_overpass_results(elements, lat, lon)
        except (httpx.HTTPError, ValueError):
            continue
    return []


def _format_overpass_results(elements: list[dict], lat: float, lon: float) -> list[dict]:
    seen = set()
    out: list[dict] = []
    for el in elements:
        tags = el.get("tags", {}) or {}
        nm = tags.get("name") or tags.get("name:en")
        if not nm:
            continue
        key = nm.strip().lower()
        if key in seen:
            continue
        seen.add(key)

        center = el.get("center") or {"lat": el.get("lat"), "lon": el.get("lon")}
        if not center.get("lat") or not center.get("lon"):
            continue
        dist = _haversine(lat, lon, center["lat"], center["lon"])

        out.append({
            "name":   nm,
            "lat":    center["lat"],
            "lon":    center["lon"],
            "dist":   dist,
            "tags":   tags,
            "category": _classify_land(nm, tags),
        })

    out.sort(key=lambda s: s["dist"])
    return out[:24]


def _land_to_spot(land: dict) -> dict:
    dist = land["dist"]
    if dist < 1:
        dist_str = "less than 1 mile"
    elif dist < 5:
        dist_str = f"{dist:.0f} miles"
    else:
        dist_str = f"~{dist:.0f} miles"

    tags = land.get("tags", {}) or {}
    operator = tags.get("operator") or tags.get("ownership") or ""
    note = []
    if operator:
        note.append(f"Managed by {operator}.")
    if tags.get("protect_class"):
        note.append(f"Protect class {tags['protect_class']}.")
    if tags.get("access"):
        note.append(f"Access: {tags['access']}.")
    description = " ".join(note) or "Public-access tract identified from OSM. Verify regulations with the state agency before hunting."

    return {
        "name":        land["name"],
        "distance":    dist_str,
        "rating":      "GOOD",
        "stars":       4,
        "featured":    False,
        "description": description,
        "game":        [],
        "tip":         "Pull the agency map, scout entry points, and check unit-specific season dates.",
        "access":      tags.get("access", "Public — verify"),
        "size":        tags.get("area") or "",
    }


# ── Curated regional fallback data ──────────────────────────────────────

_CURATED_SPOTS: dict[str, dict] = {
    "northeast_appalachian": {
        "intro": "The Appalachian belt offers some of the deepest public-land deer, bear, and turkey hunting east of the Mississippi.",
        "forests": [
            {"name": "Allegheny National Forest", "distance": "northwest PA", "rating": "HOT", "stars": 5, "featured": True,
             "description": "513,000 acres of contiguous oak-cherry forest with strong deer, black bear, and ruffed grouse populations.",
             "game": ["White-tailed Deer", "Black Bear", "Ruffed Grouse", "Wild Turkey"],
             "tip": "Hunt the cherry-clearcut edges for grouse early, and ridge-saddle funnels at peak rut for bucks.",
             "access": "Open public — PA hunting license", "size": "513,000 acres"},
            {"name": "Monongahela National Forest (WV)", "distance": "central WV", "rating": "HOT", "stars": 5, "featured": False,
             "description": "919,000 acres of high Appalachian timber — trophy-class bears and oak-mast deer hunting.",
             "game": ["White-tailed Deer", "Black Bear", "Wild Turkey", "Ruffed Grouse"],
             "tip": "Black bear hunting is exceptional. Glass burns and beech ridges in early fall mast crop.",
             "access": "WV hunting license", "size": "919,000 acres"},
            {"name": "Green Mountain National Forest (VT)", "distance": "central VT", "rating": "GOOD", "stars": 4, "featured": False,
             "description": "400,000 acres of mixed northern hardwoods. Big-woods deer hunting and trophy bear.",
             "game": ["White-tailed Deer", "Black Bear", "Moose"],
             "tip": "Track snow-cover bucks on long ridges; calling in moose only with a tag.",
             "access": "VT hunting license", "size": "400,000 acres"},
        ],
        "wmas": [
            {"name": "PA State Game Lands #57", "distance": "northeast PA", "rating": "HOT", "stars": 5, "featured": True,
             "description": "47,000 acres of remote Sullivan/Wyoming county public ground — strong deer, bear, and turkey populations.",
             "game": ["White-tailed Deer", "Black Bear", "Wild Turkey"],
             "tip": "Walk in deep on game-land roads — pressure drops by mile two.",
             "access": "Open access — PGC regulations", "size": "47,000 acres"},
            {"name": "Sproul State Forest (PA)", "distance": "central PA", "rating": "GOOD", "stars": 4, "featured": False,
             "description": "Pennsylvania's largest state forest — 305,000 acres of remote big woods.",
             "game": ["White-tailed Deer", "Black Bear", "Coyote"],
             "tip": "Use topographic maps to identify rim benches and saddles between bedrock plateaus.",
             "access": "DCNR — open public", "size": "305,000 acres"},
        ],
        "refuges": [
            {"name": "Erie National Wildlife Refuge", "distance": "northwest PA", "rating": "FAIR", "stars": 3, "featured": False,
             "description": "Limited managed waterfowl and upland hunts via lottery and walk-in zones.",
             "game": ["Wood Duck", "Mallard", "White-tailed Deer"],
             "tip": "Apply early for waterfowl draws; check the refuge hunt brochure for permitted units.",
             "access": "Refuge permit required", "size": "8,800 acres"},
        ],
    },
    "southeast": {
        "intro": "The Southeast combines vast national forest blocks with WMAs and private-leased pine country — strong deer, hog, and turkey.",
        "forests": [
            {"name": "Daniel Boone National Forest (KY)", "distance": "eastern KY", "rating": "HOT", "stars": 5, "featured": True,
             "description": "708,000 acres of Cumberland Plateau hardwoods — outstanding white-tail and turkey hunting.",
             "game": ["White-tailed Deer", "Wild Turkey", "Eastern Gray Squirrel"],
             "tip": "Hunt mast ridges in October; rim drainages funnel cruising bucks during rut.",
             "access": "KY hunting license", "size": "708,000 acres"},
            {"name": "Ocala National Forest (FL)", "distance": "north-central FL", "rating": "GOOD", "stars": 4, "featured": False,
             "description": "Sandhill scrub and oak — good deer and hog, plus some of the south's best dove fields.",
             "game": ["White-tailed Deer", "Wild Hog", "Wild Turkey", "Mourning Dove"],
             "tip": "Hogs cruise the palmetto edges at dawn; bow seasons run long in FL.",
             "access": "FL hunt permit + WMA stamp", "size": "388,000 acres"},
        ],
        "wmas": [
            {"name": "Cherokee WMA (GA)", "distance": "north GA", "rating": "HOT", "stars": 5, "featured": True,
             "description": "27,000 acres of north-Georgia hardwood ridges — quality deer and bear.",
             "game": ["White-tailed Deer", "Black Bear", "Wild Turkey"],
             "tip": "Acorn ridges hold deer through October; bear pursuit on the high benches.",
             "access": "GA WMA stamp", "size": "27,000 acres"},
        ],
        "refuges": [],
    },
    "midwest_farmbelt": {
        "intro": "The corn-and-bean belt — Iowa and Illinois trophy whitetails, Kansas pheasants, and Missouri turkey country.",
        "forests": [
            {"name": "Mark Twain National Forest (MO)", "distance": "central/southern MO", "rating": "HOT", "stars": 5, "featured": True,
             "description": "1.5 million acres of Ozark oak-hickory — Missouri's best public-land deer and turkey.",
             "game": ["White-tailed Deer", "Wild Turkey", "Eastern Gray Squirrel"],
             "tip": "Trophy bucks come off white-oak ridges; turkey hunters work the river-bottom roost trees.",
             "access": "MO hunting license", "size": "1.5M acres"},
        ],
        "wmas": [
            {"name": "Stephen A. Forbes State Park (IL)", "distance": "south IL", "rating": "GOOD", "stars": 4, "featured": True,
             "description": "Public IL deer/turkey ground in the heart of trophy country.",
             "game": ["White-tailed Deer", "Wild Turkey"],
             "tip": "Apply for IL deer permits early — public-land days are limited.",
             "access": "IL hunting license + permit", "size": "3,000 acres"},
            {"name": "Cedar Bluff Wildlife Area (KS)", "distance": "western KS", "rating": "HOT", "stars": 4, "featured": False,
             "description": "Plains-edge habitat with a mix of grassland, brush, and ag — pheasant and deer.",
             "game": ["Ring-necked Pheasant", "White-tailed Deer", "Bobwhite Quail"],
             "tip": "Hit the cattail draws after a cold snap — pheasants pile in after harvest.",
             "access": "KS WIHA + license", "size": "9,000 acres"},
        ],
        "refuges": [],
    },
    "great_plains": {
        "intro": "Big-sky country — pronghorn, mule deer, sharptails, and one of America's longest pheasant seasons.",
        "forests": [
            {"name": "Black Hills National Forest (SD/WY)", "distance": "western SD", "rating": "HOT", "stars": 5, "featured": True,
             "description": "1.25 million acres of pine-oak transition — exceptional whitetail, mule deer, and elk.",
             "game": ["White-tailed Deer", "Mule Deer", "Rocky Mountain Elk", "Wild Turkey"],
             "tip": "Apply for limited-draw elk; OTC deer in many units. Glass at first light from logging-road overlooks.",
             "access": "SD/WY licenses by unit", "size": "1.25M acres"},
        ],
        "wmas": [
            {"name": "Buffalo Gap National Grassland (SD)", "distance": "western SD", "rating": "HOT", "stars": 4, "featured": True,
             "description": "591,000 acres of mixed-grass prairie — pronghorn, mule deer, and prairie dogs.",
             "game": ["Pronghorn", "Mule Deer", "Sharp-tailed Grouse", "Prairie Dog"],
             "tip": "Spot-and-stalk pronghorn from coulees; sharptails on ridge benches early morning.",
             "access": "SD license by unit", "size": "591,000 acres"},
            {"name": "Ft. Pierre National Grassland (SD)", "distance": "central SD", "rating": "GOOD", "stars": 4, "featured": False,
             "description": "116,000 acres of tallgrass prairie — sharptails, prairie chicken, deer.",
             "game": ["Sharp-tailed Grouse", "White-tailed Deer", "Pronghorn"],
             "tip": "Hunt the lek edges October-November after the leaves drop.",
             "access": "Open public — SD license", "size": "116,000 acres"},
        ],
        "refuges": [],
    },
    "rocky_mountains": {
        "intro": "America's western big-game backbone — elk, mule deer, sheep, and bear country with millions of public acres.",
        "forests": [
            {"name": "Bridger-Teton National Forest (WY)", "distance": "western WY", "rating": "HOT", "stars": 5, "featured": True,
             "description": "3.4 million acres of high country — trophy elk, mule deer, moose, sheep, and bear.",
             "game": ["Rocky Mountain Elk", "Mule Deer", "Moose", "Black Bear", "Bighorn Sheep"],
             "tip": "Pre-season scout via OnX; horseback-camp deep on backcountry trails for less pressure.",
             "access": "WY draw or OTC by unit", "size": "3.4M acres"},
            {"name": "Bitterroot National Forest (MT/ID)", "distance": "western MT", "rating": "HOT", "stars": 5, "featured": False,
             "description": "1.6 million acres straddling the Bitterroot Range — elk, mule deer, mountain lion.",
             "game": ["Rocky Mountain Elk", "Mule Deer", "Mountain Lion", "Black Bear"],
             "tip": "Glass burns from 2007 fires for elk — regrowth holds heavy bull traffic.",
             "access": "MT/ID licenses by unit", "size": "1.6M acres"},
        ],
        "wmas": [
            {"name": "Wall Creek WMA (MT)", "distance": "southwest MT", "rating": "HOT", "stars": 5, "featured": True,
             "description": "Premier elk wintering area open to general-tag hunting in early season.",
             "game": ["Rocky Mountain Elk", "Mule Deer"],
             "tip": "Big bulls migrate through in late October — get above and glass.",
             "access": "MT general license", "size": "10,000 acres"},
        ],
        "refuges": [],
    },
    "pacific_northwest": {
        "intro": "From the wet Coast Range to the dry east-side basins — Roosevelt elk, blacktails, mule deer, and bear.",
        "forests": [
            {"name": "Olympic National Forest (WA)", "distance": "Olympic Peninsula", "rating": "HOT", "stars": 5, "featured": True,
             "description": "633,000 acres of temperate rainforest — Roosevelt elk, blacktail deer, black bear.",
             "game": ["Roosevelt Elk", "Black-tailed Deer", "Black Bear"],
             "tip": "Hunt logging cuts and burn edges; thermals are everything on the wet west side.",
             "access": "WA license by unit", "size": "633,000 acres"},
            {"name": "Umatilla National Forest (OR/WA)", "distance": "Blue Mountains", "rating": "HOT", "stars": 4, "featured": False,
             "description": "1.4 million acres in the Blue Mountains — Rocky Mountain elk, mulies, bear.",
             "game": ["Rocky Mountain Elk", "Mule Deer", "Black Bear"],
             "tip": "OR controlled hunts are the trophy ticket; OTC tags in selected units.",
             "access": "OR/WA tags by unit", "size": "1.4M acres"},
        ],
        "wmas": [],
        "refuges": [],
    },
    "california": {
        "intro": "California public-land hunting — D-zone blacktails, A-zone hogs, tule elk drawings.",
        "forests": [
            {"name": "Mendocino National Forest", "distance": "north Coast Range", "rating": "GOOD", "stars": 4, "featured": True,
             "description": "913,000 acres of remote Coast Range timber — blacktails, bear, hogs.",
             "game": ["Black-tailed Deer", "Wild Hog", "Black Bear"],
             "tip": "D-zone is OTC; pack the rifle in deep — pressure drops with elevation.",
             "access": "CA D-zone tag", "size": "913,000 acres"},
        ],
        "wmas": [
            {"name": "Tehama Wildlife Area", "distance": "northern CA", "rating": "HOT", "stars": 4, "featured": True,
             "description": "47,000-acre managed deer and turkey area — drawings for premium hunts.",
             "game": ["Black-tailed Deer", "Wild Turkey"],
             "tip": "Apply for the X-zone draw; spring turkey is open-access.",
             "access": "CA license + draw", "size": "47,000 acres"},
        ],
        "refuges": [],
    },
    "southwest_desert": {
        "intro": "The Southwest — Coues deer, desert mulies, javelina, and quail country across millions of BLM acres.",
        "forests": [
            {"name": "Coronado National Forest (AZ)", "distance": "southern AZ", "rating": "HOT", "stars": 5, "featured": True,
             "description": "1.7 million acres of sky islands — Coues deer, javelina, Mearns' quail.",
             "game": ["Coues Deer", "Mule Deer", "Javelina", "Mearns' Quail"],
             "tip": "Glass shadow lines from a high vantage; Coues bedded where you'd never expect.",
             "access": "AZ draw + OTC", "size": "1.7M acres"},
        ],
        "wmas": [
            {"name": "BLM Sonoran Desert NM", "distance": "south-central AZ", "rating": "GOOD", "stars": 4, "featured": True,
             "description": "486,000 acres of saguaro-paloverde — javelina, mule deer, Gambel's quail.",
             "game": ["Mule Deer", "Javelina", "Gambel's Quail"],
             "tip": "Tank-water sites are the X — sit downwind on warm afternoons.",
             "access": "BLM open + AZ tags", "size": "486,000 acres"},
        ],
        "refuges": [],
    },
    "great_lakes_northwoods": {
        "intro": "The big woods — northern Wisconsin, the U.P. of Michigan, and the Boundary Waters region.",
        "forests": [
            {"name": "Chequamegon-Nicolet National Forest (WI)", "distance": "northern WI", "rating": "HOT", "stars": 5, "featured": True,
             "description": "1.5 million acres of northern hardwoods — whitetail, bear, grouse, woodcock.",
             "game": ["White-tailed Deer", "Black Bear", "Ruffed Grouse", "Woodcock"],
             "tip": "Bear baiting permitted; grouse coverts on alder edges are some of the best in the country.",
             "access": "WI license", "size": "1.5M acres"},
            {"name": "Hiawatha National Forest (MI U.P.)", "distance": "Michigan U.P.", "rating": "HOT", "stars": 4, "featured": False,
             "description": "880,000 acres of mixed conifer — northern Michigan deer, bear, grouse.",
             "game": ["White-tailed Deer", "Black Bear", "Ruffed Grouse"],
             "tip": "Cedar swamp edges hold bedded deer through deep snow. Track storms.",
             "access": "MI license", "size": "880,000 acres"},
        ],
        "wmas": [],
        "refuges": [],
    },
    "alaska": {
        "intro": "The last frontier — moose, caribou, brown bear, and the wildest hunts on the continent.",
        "forests": [
            {"name": "Tongass National Forest", "distance": "Southeast AK", "rating": "HOT", "stars": 5, "featured": True,
             "description": "16.7 million acres of temperate rainforest — Sitka blacktail, brown bear, mountain goat.",
             "game": ["Sitka Black-tailed Deer", "Brown Bear", "Mountain Goat", "Black Bear"],
             "tip": "Boat-based hunts are standard; deer high on alpine ridges in summer, beach edges in winter.",
             "access": "AK license + tags", "size": "16.7M acres"},
        ],
        "wmas": [
            {"name": "Mulchatna Caribou Range (BLM)", "distance": "southwest AK", "rating": "HOT", "stars": 5, "featured": True,
             "description": "Vast remote tundra holding the Mulchatna caribou herd plus moose and brown bear.",
             "game": ["Caribou", "Moose", "Brown Bear"],
             "tip": "Fly-in hunts only — confirm transporters book a season in advance.",
             "access": "AK tags + transporter", "size": "millions of acres"},
        ],
        "refuges": [],
    },
}


# ── Build spots ─────────────────────────────────────────────────────────

async def discover_spots(lat: float, lon: float, name: str) -> dict:
    """Find nearby public hunting lands, preferring live OSM data, falling back to curated regional sets."""
    forests: list[dict] = []
    wmas: list[dict] = []
    refuges: list[dict] = []

    osm_lands = await _discover_overpass(lat, lon)
    for land in osm_lands:
        spot = _land_to_spot(land)
        cat = land["category"]
        if cat == "wma" and len(wmas) < 5:
            wmas.append(spot)
        elif cat == "forest" and len(forests) < 5:
            if not forests:
                spot["featured"] = True
                spot["rating"] = "HOT"
                spot["stars"] = 5
            forests.append(spot)
        elif cat == "refuge" and len(refuges) < 5:
            refuges.append(spot)
        elif len(forests) < 5:
            forests.append(spot)

    has_live_data = any([forests, wmas, refuges])

    region_id = _lat_lon_to_region(lat, lon)
    curated = _CURATED_SPOTS.get(region_id) if region_id else None

    if curated:
        if not forests and curated.get("forests"):
            forests = curated["forests"][:5]
        if not wmas and curated.get("wmas"):
            wmas = curated["wmas"][:5]
        if not refuges and curated.get("refuges"):
            refuges = curated["refuges"][:5]

    if has_live_data:
        intro = f"Public hunting lands near {name} discovered from OpenStreetMap protected-area data. Always verify regulations with the managing agency."
    elif curated:
        intro = curated.get("intro", "Curated regional hunting lands.")
    else:
        intro = f"No public-land matches for {name} — try a nearby city, state forest, or WMA name."

    return {
        "intro":   intro,
        "forests": forests,
        "wmas":    wmas,
        "refuges": refuges,
    }
