"""
Algorithmic hunting intelligence engine.

Deterministic scoring based on weather, season, and lunar conditions plus
regional game databases, activity predictions, and tactical tips.
"""

from datetime import datetime, timedelta
import math

# ── Regional game database keyed by region ID ────────────────────────────
#
# rutMonths: months of peak rut / breeding activity (most active sign).
# season: hunting seasons in which the species is commonly pursued
# (spring/summer/fall/winter — used for activity scoring).
# tempIdeal: low/high air-temp window where the animal moves most freely.

_REGION_GAME: dict[str, list[dict]] = {
    "northeast_appalachian": [
        {"name": "White-tailed Deer",  "tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [11], "category": "big_game"},
        {"name": "Black Bear",         "tempIdeal": [30, 65], "season": ["fall"],            "rutMonths": [6, 7], "category": "big_game"},
        {"name": "Eastern Wild Turkey","tempIdeal": [40, 70], "season": ["spring", "fall"],  "rutMonths": [4, 5], "category": "upland"},
        {"name": "Ruffed Grouse",      "tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [4],   "category": "upland"},
        {"name": "Eastern Coyote",     "tempIdeal": [10, 55], "season": ["fall", "winter"], "rutMonths": [2],   "category": "predator"},
        {"name": "Cottontail Rabbit",  "tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [3],   "category": "small_game"},
        {"name": "Gray Squirrel",      "tempIdeal": [30, 70], "season": ["fall"],            "rutMonths": [1, 6], "category": "small_game"},
        {"name": "Red Fox",            "tempIdeal": [10, 50], "season": ["winter"],          "rutMonths": [1, 2], "category": "predator"},
    ],
    "southeast": [
        {"name": "White-tailed Deer",  "tempIdeal": [35, 65], "season": ["fall", "winter"], "rutMonths": [11, 1], "category": "big_game"},
        {"name": "Wild Hog",           "tempIdeal": [35, 75], "season": ["fall", "winter", "spring", "summer"], "rutMonths": [1, 6], "category": "big_game"},
        {"name": "Eastern Wild Turkey","tempIdeal": [45, 75], "season": ["spring"],          "rutMonths": [4],     "category": "upland"},
        {"name": "Bobwhite Quail",     "tempIdeal": [40, 65], "season": ["fall", "winter"], "rutMonths": [5],     "category": "upland"},
        {"name": "Wood Duck",          "tempIdeal": [25, 60], "season": ["fall", "winter"], "rutMonths": [2],     "category": "waterfowl"},
        {"name": "Mourning Dove",      "tempIdeal": [50, 85], "season": ["fall"],            "rutMonths": [4, 5],  "category": "upland"},
        {"name": "Squirrel",           "tempIdeal": [35, 75], "season": ["fall"],            "rutMonths": [1, 6],  "category": "small_game"},
        {"name": "Coyote",             "tempIdeal": [20, 65], "season": ["fall", "winter"], "rutMonths": [2],     "category": "predator"},
    ],
    "midwest_farmbelt": [
        {"name": "White-tailed Deer",  "tempIdeal": [20, 55], "season": ["fall", "winter"], "rutMonths": [11],    "category": "big_game"},
        {"name": "Eastern Wild Turkey","tempIdeal": [40, 70], "season": ["spring", "fall"],  "rutMonths": [4, 5],  "category": "upland"},
        {"name": "Ring-necked Pheasant","tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [4],     "category": "upland"},
        {"name": "Mallard",            "tempIdeal": [20, 55], "season": ["fall", "winter"], "rutMonths": [3],     "category": "waterfowl"},
        {"name": "Canada Goose",       "tempIdeal": [15, 55], "season": ["fall", "winter"], "rutMonths": [3],     "category": "waterfowl"},
        {"name": "Cottontail Rabbit",  "tempIdeal": [20, 55], "season": ["fall", "winter"], "rutMonths": [3],     "category": "small_game"},
        {"name": "Coyote",             "tempIdeal": [10, 55], "season": ["fall", "winter"], "rutMonths": [2],     "category": "predator"},
    ],
    "great_plains": [
        {"name": "White-tailed Deer",  "tempIdeal": [15, 55], "season": ["fall", "winter"], "rutMonths": [11],    "category": "big_game"},
        {"name": "Mule Deer",          "tempIdeal": [15, 55], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Pronghorn",          "tempIdeal": [35, 75], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Sharp-tailed Grouse","tempIdeal": [20, 55], "season": ["fall"],            "rutMonths": [4],     "category": "upland"},
        {"name": "Ring-necked Pheasant","tempIdeal": [20, 55], "season": ["fall", "winter"], "rutMonths": [4],     "category": "upland"},
        {"name": "Mallard",            "tempIdeal": [15, 50], "season": ["fall", "winter"], "rutMonths": [3],     "category": "waterfowl"},
        {"name": "Coyote",             "tempIdeal": [5, 55],  "season": ["fall", "winter"], "rutMonths": [2],     "category": "predator"},
        {"name": "Prairie Dog",        "tempIdeal": [55, 85], "season": ["spring", "summer", "fall"], "rutMonths": [3], "category": "varmint"},
    ],
    "rocky_mountains": [
        {"name": "Rocky Mountain Elk", "tempIdeal": [20, 60], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Mule Deer",          "tempIdeal": [15, 55], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Black Bear",         "tempIdeal": [30, 65], "season": ["fall", "spring"], "rutMonths": [6, 7],  "category": "big_game"},
        {"name": "Pronghorn",          "tempIdeal": [35, 75], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Bighorn Sheep",      "tempIdeal": [15, 55], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Mountain Goat",      "tempIdeal": [10, 50], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Mountain Lion",      "tempIdeal": [10, 50], "season": ["winter"],          "rutMonths": [12, 1, 2], "category": "predator"},
        {"name": "Blue Grouse",        "tempIdeal": [20, 55], "season": ["fall"],            "rutMonths": [4, 5],  "category": "upland"},
    ],
    "pacific_northwest": [
        {"name": "Roosevelt Elk",      "tempIdeal": [30, 60], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Black-tailed Deer",  "tempIdeal": [30, 65], "season": ["fall"],            "rutMonths": [11],    "category": "big_game"},
        {"name": "Mule Deer",          "tempIdeal": [20, 55], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Black Bear",         "tempIdeal": [30, 65], "season": ["fall", "spring"], "rutMonths": [6, 7],  "category": "big_game"},
        {"name": "Mountain Lion",      "tempIdeal": [10, 50], "season": ["winter"],          "rutMonths": [12, 1, 2], "category": "predator"},
        {"name": "Ruffed Grouse",      "tempIdeal": [25, 55], "season": ["fall"],            "rutMonths": [4],     "category": "upland"},
        {"name": "Blue Grouse",        "tempIdeal": [20, 55], "season": ["fall"],            "rutMonths": [4, 5],  "category": "upland"},
    ],
    "california": [
        {"name": "Black-tailed Deer",  "tempIdeal": [40, 70], "season": ["fall"],            "rutMonths": [11],    "category": "big_game"},
        {"name": "Mule Deer",          "tempIdeal": [30, 65], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Wild Hog",           "tempIdeal": [40, 80], "season": ["fall", "winter", "spring", "summer"], "rutMonths": [1, 6], "category": "big_game"},
        {"name": "Tule Elk",           "tempIdeal": [30, 65], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Wild Turkey",        "tempIdeal": [45, 75], "season": ["spring", "fall"],  "rutMonths": [3, 4],  "category": "upland"},
        {"name": "Mountain Quail",     "tempIdeal": [35, 65], "season": ["fall"],            "rutMonths": [4],     "category": "upland"},
        {"name": "Mountain Lion",      "tempIdeal": [20, 55], "season": ["winter"],          "rutMonths": [12, 1], "category": "predator"},
    ],
    "southwest_desert": [
        {"name": "Mule Deer",          "tempIdeal": [35, 70], "season": ["fall"],            "rutMonths": [12, 1], "category": "big_game"},
        {"name": "Coues Deer",         "tempIdeal": [40, 75], "season": ["fall", "winter"], "rutMonths": [12, 1], "category": "big_game"},
        {"name": "Desert Bighorn",     "tempIdeal": [40, 75], "season": ["fall", "winter"], "rutMonths": [8, 9],  "category": "big_game"},
        {"name": "Pronghorn",          "tempIdeal": [40, 80], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Javelina",           "tempIdeal": [45, 80], "season": ["fall", "winter"], "rutMonths": [10],    "category": "big_game"},
        {"name": "Gambel's Quail",     "tempIdeal": [40, 75], "season": ["fall", "winter"], "rutMonths": [4],     "category": "upland"},
        {"name": "Mearns' Quail",      "tempIdeal": [35, 70], "season": ["winter"],          "rutMonths": [7],     "category": "upland"},
        {"name": "Mountain Lion",      "tempIdeal": [25, 60], "season": ["winter"],          "rutMonths": [12],    "category": "predator"},
    ],
    "alaska": [
        {"name": "Moose",              "tempIdeal": [15, 50], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Caribou",            "tempIdeal": [10, 45], "season": ["fall"],            "rutMonths": [10],    "category": "big_game"},
        {"name": "Brown Bear",         "tempIdeal": [25, 60], "season": ["fall", "spring"], "rutMonths": [5, 6],  "category": "big_game"},
        {"name": "Black Bear",         "tempIdeal": [25, 60], "season": ["fall", "spring"], "rutMonths": [6, 7],  "category": "big_game"},
        {"name": "Dall Sheep",         "tempIdeal": [10, 45], "season": ["fall"],            "rutMonths": [11, 12],"category": "big_game"},
        {"name": "Sitka Black-tailed Deer", "tempIdeal": [25, 55], "season": ["fall"],       "rutMonths": [11],    "category": "big_game"},
        {"name": "Ptarmigan",          "tempIdeal": [-5, 35], "season": ["fall", "winter"], "rutMonths": [4],     "category": "upland"},
    ],
    "great_lakes_northwoods": [
        {"name": "White-tailed Deer",  "tempIdeal": [15, 50], "season": ["fall", "winter"], "rutMonths": [11],    "category": "big_game"},
        {"name": "Black Bear",         "tempIdeal": [30, 65], "season": ["fall"],            "rutMonths": [6, 7],  "category": "big_game"},
        {"name": "Moose",              "tempIdeal": [10, 45], "season": ["fall"],            "rutMonths": [9, 10], "category": "big_game"},
        {"name": "Ruffed Grouse",      "tempIdeal": [20, 55], "season": ["fall", "winter"], "rutMonths": [4],     "category": "upland"},
        {"name": "Woodcock",           "tempIdeal": [35, 65], "season": ["fall"],            "rutMonths": [4],     "category": "upland"},
        {"name": "Mallard",            "tempIdeal": [15, 50], "season": ["fall", "winter"], "rutMonths": [3],     "category": "waterfowl"},
        {"name": "Eastern Wild Turkey","tempIdeal": [40, 70], "season": ["spring", "fall"],  "rutMonths": [4, 5],  "category": "upland"},
        {"name": "Coyote",             "tempIdeal": [-5, 50], "season": ["fall", "winter"], "rutMonths": [2],     "category": "predator"},
    ],
}

# Fall-back mixed list when no region matches
_DEFAULT_GAME = [
    {"name": "White-tailed Deer",  "tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [11], "category": "big_game"},
    {"name": "Wild Turkey",        "tempIdeal": [40, 70], "season": ["spring", "fall"],  "rutMonths": [4, 5], "category": "upland"},
    {"name": "Cottontail Rabbit",  "tempIdeal": [25, 55], "season": ["fall", "winter"], "rutMonths": [3], "category": "small_game"},
    {"name": "Gray Squirrel",      "tempIdeal": [30, 70], "season": ["fall"],            "rutMonths": [1, 6], "category": "small_game"},
    {"name": "Coyote",             "tempIdeal": [10, 55], "season": ["fall", "winter"], "rutMonths": [2], "category": "predator"},
    {"name": "Mourning Dove",      "tempIdeal": [50, 85], "season": ["fall"],            "rutMonths": [4, 5], "category": "upland"},
]

# ── Region bounding boxes [s_lat, w_lon, n_lat, e_lon] ──────────────────
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


def _get_season(month: int, lat: float) -> str:
    if lat >= 0:
        if month in (12, 1, 2):
            return "winter"
        if month in (3, 4, 5):
            return "spring"
        if month in (6, 7, 8):
            return "summer"
        return "fall"
    if month in (12, 1, 2):
        return "summer"
    if month in (3, 4, 5):
        return "fall"
    if month in (6, 7, 8):
        return "winter"
    return "spring"


# ── Scoring ──────────────────────────────────────────────────────────────

def compute_hourly_score(
    hour: int,
    temp_f: float | None,
    wind_mph: float | None,
    cloud_pct: float | None,
    pressure: float | None,
    pressure_delta_24h: float | None,
    pressure_delta_6h: float | None,
    precip_mm: float | None,
    moon_illum: float,
    is_daylight: bool,
    near_dawn: bool,
    near_dusk: bool,
) -> tuple[int, list[str]]:
    """Score one hour 0-100, plus a list of factor labels that contributed.

    Factor labels are short strings ("rising barometer", "cold front edge",
    "prime dusk window") so the UI can explain *why* an hour scored high.
    """
    s = 50
    factors: list[str] = []

    # ── Time of day ─────────────────────────────────────────────────
    # Dawn and dusk are weighted off solar geometry, not a fixed clock,
    # because sunrise drifts an hour across the year.
    if near_dawn:
        s += 22
        factors.append("dawn window")
    elif near_dusk:
        s += 20
        factors.append("dusk window")
    elif is_daylight:
        if 11 <= hour <= 14:
            s -= 8
            factors.append("midday lull")
        else:
            s += 2
    else:
        s -= 6  # full dark — scoring this for legal-light species only

    # ── Air temperature ──────────────────────────────────────────────
    if temp_f is not None:
        if 25 <= temp_f <= 50:
            s += 14
            factors.append("cool temps")
        elif 50 < temp_f <= 65:
            s += 6
        elif 15 <= temp_f < 25:
            s += 4
            factors.append("cold push")
        elif temp_f < 5 or temp_f > 80:
            s -= 14
            factors.append("temp stress")
        elif temp_f > 70:
            s -= 6
            factors.append("warm hold")

    # ── Wind ─────────────────────────────────────────────────────────
    if wind_mph is not None:
        if 3 <= wind_mph <= 10:
            s += 12
            factors.append("steady wind")
        elif wind_mph < 3:
            s += 2  # thermals dominate; not bad but not ideal
        elif wind_mph < 15:
            s -= 2
        elif wind_mph < 22:
            s -= 10
            factors.append("strong wind")
        else:
            s -= 18
            factors.append("gale")

    # ── Pressure trend (the meat of the hunting science) ────────────
    # The classic deer-movement trigger isn't an absolute pressure value,
    # it's the *change*. Three high-value patterns:
    #   1. Falling sharply → "front edge" — animals feed hard ahead of weather
    #   2. Rising into a high after a front passes → strongest movement window
    #   3. Stable high → solid steady activity
    # The trap to avoid: rating "high pressure" alone, which can also be a
    # post-front bluebird crash with depressed activity.
    if pressure_delta_6h is not None and pressure_delta_6h <= -2.5:
        s += 10
        factors.append("front edge")
    if pressure_delta_24h is not None:
        if pressure_delta_24h >= 5 and pressure is not None and pressure >= 1015:
            s += 14
            factors.append("rising into high")
        elif pressure_delta_24h >= 2:
            s += 6
            factors.append("rising barometer")
        elif pressure_delta_24h <= -5:
            # Falling fast — front incoming is good (caught by 6h above);
            # but if it's been falling all day we're past the bite window.
            if pressure_delta_6h is None or pressure_delta_6h > -2.5:
                s -= 4
                factors.append("falling pressure")
        elif -1 <= pressure_delta_24h <= 1 and pressure is not None:
            # Stable. Discriminate by absolute level.
            if pressure >= 1020:
                s += 6
                factors.append("stable high")
            elif pressure < 1008:
                s -= 6
                factors.append("stable low")

    # ── Cloud cover ──────────────────────────────────────────────────
    if cloud_pct is not None:
        if 30 <= cloud_pct <= 70:
            s += 4
        elif cloud_pct > 95:
            s -= 2

    # ── Precipitation (mm/hour at this hour) ─────────────────────────
    if precip_mm is not None:
        if precip_mm > 2.5:
            s -= 14
            factors.append("heavy rain")
        elif precip_mm > 0.5:
            s -= 4
            factors.append("rain")
        # light drizzle (0 < x <= 0.5) is neutral — can even help

    # ── Moon ─────────────────────────────────────────────────────────
    if moon_illum > 0.85 and is_daylight:
        s -= 6
        factors.append("full-moon nocturnal feeding")
    elif moon_illum < 0.15 and is_daylight:
        s += 3
        factors.append("dark moon")

    return max(0, min(100, round(s))), factors


# ── Per-species activity ─────────────────────────────────────────────────

def _species_activity(
    game: dict,
    temp_f: float | None,
    wind_mph: float | None,
    pressure: float | None,
    current_season: str,
    current_month: int,
    hour: int,
) -> tuple[str, str]:
    score = 50

    if current_season in game.get("season", []):
        score += 16
    else:
        score -= 22

    rut_months = set(game.get("rutMonths", []))
    if current_month in rut_months:
        score += 18

    if temp_f is not None:
        lo, hi = game.get("tempIdeal", [25, 65])
        mid = (lo + hi) / 2
        if lo <= temp_f <= hi:
            closeness = 1 - abs(temp_f - mid) / ((hi - lo) / 2 + 1)
            score += int(18 * closeness)
        else:
            delta = min(abs(temp_f - lo), abs(temp_f - hi))
            score -= min(18, int(delta / 2))

    if wind_mph is not None:
        if 3 <= wind_mph <= 10:
            score += 6
        elif wind_mph > 20:
            score -= 12
        elif wind_mph > 15:
            score -= 5

    if pressure is not None:
        if pressure >= 1020:
            score += 5
        elif pressure < 1008:
            score -= 5

    if 5 <= hour <= 8 or 16 <= hour <= 19:
        score += 10
    elif 11 <= hour <= 14:
        score -= 6

    if score >= 75:
        activity = "HOT"
    elif score >= 55:
        activity = "ACTIVE"
    elif score >= 35:
        activity = "FAIR"
    else:
        activity = "SLOW"

    tip = _generate_tip(game["name"], game.get("category", ""), activity, current_season, current_month, temp_f, wind_mph, hour, rut_months)
    return activity, tip


def _generate_tip(name: str, category: str, activity: str, season: str, month: int, temp: float | None, wind: float | None, hour: int, rut_months: set[int]) -> str:
    n = name.lower()
    in_rut = month in rut_months

    if "deer" in n and "mule" not in n and "black-tailed" not in n and "coues" not in n and "sitka" not in n:
        if in_rut:
            return "Pre-rut and rut activity — sit all-day on funnels between bedding and doe groups. Rattling and grunting are productive."
        if season == "fall" and temp is not None and temp < 35:
            return "Cold front pushes deer onto food early. Hunt evening sits over white oak ridges or standing beans."
        if hour < 9:
            return "First-light is prime — set up downwind of food-to-bed travel routes."
        if hour > 16:
            return "Last hour is critical — get on a destination food source with the wind in your face."
        return "Mid-day post-up on a bedding-area pinch can produce when bucks shift beds."

    if "mule deer" in n or "black-tailed" in n or "coues" in n:
        if in_rut:
            return "Rut is on — glass open south-facing slopes for cruising bucks chasing does."
        return "Glass at first and last light from elevated knobs — mulies bed in cover, feed open edges."

    if "elk" in n:
        if month in (9, 10):
            return "Bugle and cow-call into north-slope dark timber and meadow edges at first light. Stay above bulls when possible."
        if season == "fall":
            return "Glass meadow fringes at dawn and dusk; still-hunt benches mid-day with the wind in your face."
        return "Locate herds from glassing knobs, then plan a wind-correct stalk."

    if "moose" in n:
        if month in (9, 10):
            return "Cow-calling and raking near willow-bottom drainages in the rut. Listen for grunts and breaking brush."
        return "Glass willow flats and burns at dawn/dusk; check beaver ponds and bog edges."

    if "caribou" in n:
        return "Glass long ridge lines and cut a route to intercept moving bands. Stay still — caribou will close on a stationary hunter."

    if "pronghorn" in n:
        return "Spot-and-stalk with terrain, or set a decoy-and-call rig in the rut. Glass from high points; antelope spook on movement, not noise."

    if "bear" in n or "boar" in n or "hog" in n:
        if "bear" in n and season == "fall":
            return "Hunt mast crops and orchard edges — black bears feed heavily before denning. Glass berry slides at first light."
        if "hog" in n or "boar" in n:
            if hour > 18 or hour < 6:
                return "Hogs feed heavily after dark — set up downwind of wallows, oak flats, and ag edges."
            return "Find rooting and fresh wallows; stalk the wind into bedding cover."
        return "Bait sites, beaver ponds, and pipeline berry slides — keep the wind crossing your scent away from approach."

    if "sheep" in n or "goat" in n:
        return "Pre-glass from a vantage that reveals adjacent basins. Plan a stalk that keeps the thermals in your face."

    if "lion" in n or "cougar" in n:
        return "Run hounds on fresh tracks after a snowfall, or call from broken country with prey-distress sounds at dawn/dusk."

    if "coyote" in n or "fox" in n:
        if season == "winter":
            return "Cold mornings post-snow are prime — set up with the wind in your face and call from elevated, broken country."
        return "Distress calls 200–400 yards into the wind. Switch sounds every 8–10 minutes; expect wide flanking approaches."

    if "javelina" in n:
        return "Glass south-facing prickly-pear slopes mid-morning when groups feed. Stalk close — javelina see poorly, smell well."

    if "turkey" in n:
        if season == "spring":
            return "Roost at dusk, set up tight at fly-down. Soft yelps and a single hen decoy work most days."
        return "Fall flock-busting — scatter, sit tight, and call them back to the break site."

    if "grouse" in n:
        return "Walk young aspen, alder edges, and skid roads. Mid-day flushes near gravel and clover."

    if "pheasant" in n:
        return "Hunt the wind, push thick CRP and cattail edges to a block. Best after a cold front."

    if "quail" in n:
        return "Mornings on shrubby creek bottoms and brush-edge food plots. Coveys hold tighter on still, cool days."

    if "woodcock" in n:
        return "Young alder run, soft moist soil — flushes are tight, get the gun up early."

    if "dove" in n:
        return "Late-afternoon water tanks and harvested grain. Set decoys in the open, hide in the shade."

    if "duck" in n or "mallard" in n or "wood duck" in n or "goose" in n:
        if season == "winter" and temp is not None and temp < 30:
            return "Hunt the X — birds will slide to whatever water stays open. Spinners and motion decoys early, drop to feeders late."
        return "Scout the day before. Feed fields for geese, flooded timber and sloughs for ducks. Set up off the corner of the wind."

    if "rabbit" in n or "cottontail" in n:
        return "Brushy fence rows and brier patches after a fresh snow. Walk slow, kick brush, then stop — rabbits flush off the second pause."

    if "squirrel" in n:
        return "Hunt mast — hickory, oak, beech. Sit still 20 minutes before moving; listen for cuttings drop."

    if "ptarmigan" in n:
        return "Walk willow flats and ridge benches near alpine. Tracks in fresh snow mark daily feeding routes."

    if "prairie dog" in n:
        return "Long range from a stable rest. Wind under 10 mph and overcast holds them up longer."

    return "Scout sign first; pick stand or stalk based on wind. Hunt the edges of cover at first and last light."


# ── Best hunting windows (derived from the hourly curve) ────────────────

def _format_hour(h: int) -> str:
    if h == 0:
        return "12 AM"
    if h < 12:
        return f"{h} AM"
    if h == 12:
        return "12 PM"
    return f"{h - 12} PM"


def _derive_best_windows(hourly: list[dict], top_n: int = 3) -> list[dict]:
    """Find contiguous spans of high-scoring hours and return the best `top_n`.

    A "window" is a run of hours where score >= max(55, day_max - 15).
    Windows separated by a single dip are merged; the result is sorted by
    peak score descending and trimmed to top_n.
    """
    if not hourly:
        return []
    day_max = max(h["score"] for h in hourly)
    threshold = max(55, day_max - 15)

    windows = []
    cur_start = None
    cur_peak = 0
    for i, h in enumerate(hourly):
        if h["score"] >= threshold:
            if cur_start is None:
                cur_start = i
                cur_peak = h["score"]
            else:
                cur_peak = max(cur_peak, h["score"])
        else:
            if cur_start is not None:
                windows.append((cur_start, i - 1, cur_peak))
                cur_start = None
                cur_peak = 0
    if cur_start is not None:
        windows.append((cur_start, len(hourly) - 1, cur_peak))

    windows.sort(key=lambda w: (-w[2], w[0]))
    out = []
    for start_idx, end_idx, peak in windows[:top_n]:
        start_h = hourly[start_idx]["hour"]
        # End label is the *start* of the last hour + 1 to feel natural
        end_h = (hourly[end_idx]["hour"] + 1) % 24
        # Build a prose label from the dominant factor at the peak
        peak_h = max(hourly[start_idx:end_idx + 1], key=lambda h: h["score"])
        why = peak_h["factors"][0] if peak_h["factors"] else "favorable conditions"
        out.append({
            "rangeLabel": f"{_format_hour(start_h)}–{_format_hour(end_h)}",
            "startHour":  start_h,
            "endHour":    end_h,
            "peakScore":  peak,
            "why":        why,
        })
    return out


# ── Moon phase ───────────────────────────────────────────────────────────

def _moon_phase(now: datetime) -> dict:
    """Approximate moon phase + illumination using a 29.53-day synodic cycle."""
    # Reference new moon: 2000-01-06 18:14 UTC
    ref = datetime(2000, 1, 6, 18, 14)
    days = (now - ref).total_seconds() / 86400.0
    cycle = 29.530588853
    phase = (days % cycle) / cycle  # 0..1, 0 = new

    illum = (1 - math.cos(2 * math.pi * phase)) / 2
    illum = round(illum, 2)

    if phase < 0.03 or phase > 0.97:
        label, icon = "NEW MOON", "🌑"
    elif phase < 0.22:
        label, icon = "WAXING CRESCENT", "🌒"
    elif phase < 0.28:
        label, icon = "FIRST QUARTER", "🌓"
    elif phase < 0.47:
        label, icon = "WAXING GIBBOUS", "🌔"
    elif phase < 0.53:
        label, icon = "FULL MOON", "🌕"
    elif phase < 0.72:
        label, icon = "WANING GIBBOUS", "🌖"
    elif phase < 0.78:
        label, icon = "LAST QUARTER", "🌗"
    else:
        label, icon = "WANING CRESCENT", "🌘"

    if illum > 0.85:
        rating, note = "POOR",   "Bright nights — animals feed nocturnally, less daylight movement."
    elif illum > 0.65:
        rating, note = "FAIR",   "Some nocturnal feeding — concentrate hunts at first/last light."
    elif illum > 0.35:
        rating, note = "GOOD",   "Balanced — daylight movement should be normal."
    elif illum > 0.10:
        rating, note = "EXCELLENT", "Dark nights — animals feed in daylight, prime conditions."
    else:
        rating, note = "EXCELLENT", "New moon — animals push hardest into daylight movement."

    return {
        "label":        label,
        "icon":         icon,
        "illumination": illum,
        "phaseFrac":    round(phase, 3),
        "rating":       rating,
        "note":         note,
    }


# ── Wind assessment ─────────────────────────────────────────────────────

_COMPASS = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"]


def _wind_assessment(wind_mph: float | None, wind_dir_deg: float | None, gust: float | None) -> dict:
    if wind_mph is None:
        return {"speedMph": None, "directionDeg": None, "compass": "—", "gustMph": None, "rating": "UNKNOWN", "note": ""}

    if wind_dir_deg is not None:
        idx = int((wind_dir_deg % 360) / 22.5 + 0.5) % 16
        compass = _COMPASS[idx]
    else:
        compass = "—"

    if 3 <= wind_mph <= 10:
        rating, note = "IDEAL", "Steady breeze — perfect for scent control and stand approach."
    elif wind_mph < 3:
        rating, note = "DEAD CALM", "Thermals will dominate. Stay above bedding and watch your scent stream."
    elif wind_mph < 15:
        rating, note = "FAIR", "Manageable — pick stands that put the wind in your face."
    elif wind_mph < 22:
        rating, note = "TOUGH", "Animals seek lee cover; hunt downwind of leeward ridge benches."
    else:
        rating, note = "POOR", "Most game stays bedded. Reschedule unless you have leeward bowls to glass."

    return {
        "speedMph":     round(wind_mph, 1),
        "directionDeg": round(wind_dir_deg, 0) if wind_dir_deg is not None else None,
        "compass":      compass,
        "gustMph":      round(gust, 1) if gust is not None else None,
        "rating":       rating,
        "note":         note,
    }


# ── Hourly slicing & scoring ────────────────────────────────────────────

def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def _score_day(weather: dict, day_index: int, moon_illum: float) -> tuple[list[dict], datetime | None, datetime | None]:
    """Score every hour of the requested day.

    Returns (hourly_score_list, sunrise_dt, sunset_dt). Each entry in the
    list is a dict with hour, score, factors, and the raw weather values
    that drove the score.
    """
    daily  = weather.get("daily", {}) or {}
    hourly = weather.get("hourly", {}) or {}

    times      = hourly.get("time") or []
    h_temp     = hourly.get("temperature_2m") or []
    h_wind     = hourly.get("wind_speed_10m") or []
    h_wdir     = hourly.get("wind_direction_10m") or []
    h_gust     = hourly.get("wind_gusts_10m") or []
    h_cloud    = hourly.get("cloud_cover") or []
    h_press    = hourly.get("pressure_msl") or []
    h_precip   = hourly.get("precipitation") or []
    h_isday    = hourly.get("is_day") or []

    day_dates  = daily.get("time") or []
    if day_index >= len(day_dates):
        return [], None, None
    target_date = day_dates[day_index]   # e.g. "2026-05-05"

    sunrise = _parse_iso((daily.get("sunrise") or [None] * 7)[day_index])
    sunset  = _parse_iso((daily.get("sunset")  or [None] * 7)[day_index])

    # Find the index where `times[i]` starts with target_date — that's hour 0
    # of the target day. Slice 24 forward.
    day_start_idx = None
    for i, t in enumerate(times):
        if t.startswith(target_date):
            day_start_idx = i
            break
    if day_start_idx is None:
        return [], sunrise, sunset

    out: list[dict] = []
    for offset in range(24):
        idx = day_start_idx + offset
        if idx >= len(times):
            break

        ts   = times[idx]
        hour = int(ts.split("T")[1].split(":")[0]) if "T" in ts else offset
        ts_dt = _parse_iso(ts)

        temp_f   = h_temp[idx]   if idx < len(h_temp)   else None
        wind_mph = h_wind[idx]   if idx < len(h_wind)   else None
        wind_dir = h_wdir[idx]   if idx < len(h_wdir)   else None
        gust     = h_gust[idx]   if idx < len(h_gust)   else None
        cloud    = h_cloud[idx]  if idx < len(h_cloud)  else None
        press    = h_press[idx]  if idx < len(h_press)  else None
        precip   = h_precip[idx] if idx < len(h_precip) else None
        is_day   = bool(h_isday[idx]) if idx < len(h_isday) else (6 <= hour <= 19)

        # Pressure trend — look back in the global hourly array
        d24 = None
        if press is not None and idx >= 24 and idx - 24 < len(h_press):
            prev24 = h_press[idx - 24]
            if prev24 is not None:
                d24 = press - prev24
        d6 = None
        if press is not None and idx >= 6 and idx - 6 < len(h_press):
            prev6 = h_press[idx - 6]
            if prev6 is not None:
                d6 = press - prev6

        near_dawn = bool(sunrise and ts_dt and abs((ts_dt - sunrise).total_seconds()) <= 5400)  # ±90min
        near_dusk = bool(sunset  and ts_dt and abs((ts_dt - sunset).total_seconds())  <= 5400)

        score, factors = compute_hourly_score(
            hour, temp_f, wind_mph, cloud, press, d24, d6, precip, moon_illum,
            is_day, near_dawn, near_dusk,
        )
        out.append({
            "hour":            hour,
            "score":           score,
            "factors":         factors,
            "tempF":           round(temp_f, 1) if temp_f is not None else None,
            "windMph":         round(wind_mph, 1) if wind_mph is not None else None,
            "windDirDeg":      round(wind_dir, 0) if wind_dir is not None else None,
            "gustMph":         round(gust, 1) if gust is not None else None,
            "cloudPct":        round(cloud, 0) if cloud is not None else None,
            "pressureHpa":     round(press, 1) if press is not None else None,
            "pressureD24":     round(d24, 1) if d24 is not None else None,
            "pressureD6":      round(d6, 1) if d6 is not None else None,
            "precipMm":        round(precip, 2) if precip is not None else None,
            "isDay":           is_day,
        })
    return out, sunrise, sunset


# ── Main entry point ─────────────────────────────────────────────────────

def build_hunting_analysis(
    lat: float,
    lon: float,
    name: str,
    weather: dict,
    terrain: dict,
    day_index: int = 0,
) -> dict:
    now            = datetime.utcnow()
    current_season = _get_season(now.month, lat)
    region_id      = _lat_lon_to_region(lat, lon)
    game_list      = _REGION_GAME.get(region_id, _DEFAULT_GAME)
    is_today       = day_index == 0

    moon = _moon_phase(now + timedelta(days=day_index))

    hourly_scores, sunrise, sunset = _score_day(weather, day_index, moon["illumination"])

    # Day-level summary stats
    if hourly_scores:
        peak_hour = max(hourly_scores, key=lambda h: h["score"])
        score = peak_hour["score"]
        # The "representative" hour for species tactics: use peak unless we're
        # in today's actual current hour, in which case use that.
        cur_hour = now.hour
        if is_today and 0 <= cur_hour < len(hourly_scores):
            ref_hour_data = hourly_scores[cur_hour]
        else:
            ref_hour_data = peak_hour
    else:
        score = 0
        ref_hour_data = None

    if score >= 80:
        verdict = "PRIME CONDITIONS"
    elif score >= 65:
        verdict = "GOOD CONDITIONS"
    elif score >= 45:
        verdict = "FAIR CONDITIONS"
    else:
        verdict = "CHALLENGING CONDITIONS"

    # Wind panel uses the reference hour (current hour today, peak otherwise)
    # so it answers "what is the wind going to feel like when I'm sitting".
    if ref_hour_data:
        ref_wind_mph = ref_hour_data["windMph"]
        ref_wind_dir = ref_hour_data["windDirDeg"]
        ref_gust     = ref_hour_data["gustMph"]
    else:
        ref_wind_mph = ref_wind_dir = ref_gust = None

    wind = _wind_assessment(ref_wind_mph, ref_wind_dir, ref_gust)

    # Insight should describe the *peak* hour — the moment the verdict is
    # rating — so headline doesn't contradict body.
    peak_data = peak_hour if hourly_scores else None
    ref_temp     = peak_data["tempF"]        if peak_data else None
    ref_pressure = peak_data["pressureHpa"]  if peak_data else None
    ref_pd24     = peak_data["pressureD24"]  if peak_data else None
    insight_wind_mph = peak_data["windMph"]  if peak_data else None

    insight_parts = []
    # Pressure-trend headline (the most actionable signal)
    if ref_pd24 is not None and ref_pressure is not None:
        if ref_pd24 >= 5 and ref_pressure >= 1015:
            insight_parts.append(f"Barometer rising into a high (+{ref_pd24:.1f} hPa / 24h) — major movement window.")
        elif ref_pd24 >= 2:
            insight_parts.append(f"Pressure climbing (+{ref_pd24:.1f} hPa / 24h) — favorable.")
        elif ref_pd24 <= -3:
            insight_parts.append(f"Pressure falling fast ({ref_pd24:.1f} hPa / 24h) — front incoming, hunt the leading edge.")
    if ref_temp is not None:
        if 25 <= ref_temp <= 50:
            insight_parts.append(f"Temps near {round(ref_temp)}°F are in the prime movement window.")
        elif ref_temp > 70:
            insight_parts.append(f"Warm ({round(ref_temp)}°F) — animals hold cover, move late.")
        elif ref_temp < 10:
            insight_parts.append(f"Bitter cold ({round(ref_temp)}°F) — heavy feeding pushes possible.")
    if insight_wind_mph is not None:
        if 3 <= insight_wind_mph <= 10:
            insight_parts.append(f"Steady {round(insight_wind_mph)} mph wind in the peak window — ideal for scent control.")
        elif insight_wind_mph > 20:
            insight_parts.append(f"Heavy wind at {round(insight_wind_mph)} mph will push animals to leeward cover.")
    insight_parts.append(moon["note"])
    if not insight_parts:
        insight_parts.append(f"Conditions near {name} are {'favorable' if score >= 55 else 'challenging'}.")
    insight = " ".join(insight_parts)

    elev = terrain.get("elevationFt") if isinstance(terrain, dict) else None
    zone = terrain.get("zone") if isinstance(terrain, dict) else None

    # Per-species activity uses the day's *peak* hour — that's the hour the
    # hunter would actually be in the field, not whatever clock-time it is.
    species_hour = ref_hour_data["hour"] if ref_hour_data else 8
    game_results = []
    for sp in game_list:
        activity, tip = _species_activity(
            sp, ref_temp, ref_wind_mph, ref_pressure, current_season, now.month, species_hour
        )
        game_results.append({
            "name":      sp["name"],
            "category":  sp.get("category", ""),
            "activity":  activity,
            "tip":       tip,
            "rut":       now.month in set(sp.get("rutMonths", [])),
            "tempIdeal": sp.get("tempIdeal"),
        })

    game_results.sort(key=lambda g: ({"HOT": 0, "ACTIVE": 1, "FAIR": 2, "SLOW": 3}.get(g["activity"], 4), 0 if g["rut"] else 1))

    best_windows = _derive_best_windows(hourly_scores)
    sunrise_hour_decimal = (sunrise.hour + sunrise.minute / 60) if sunrise else None
    sunset_hour_decimal  = (sunset.hour + sunset.minute / 60)   if sunset  else None

    day_times = (weather.get("daily") or {}).get("time") or []
    day_label = day_times[day_index] if day_index < len(day_times) else ("today" if is_today else "")

    return {
        "score":         score,
        "verdict":       verdict,
        "insight":       insight,
        "game":          game_results[:10],
        "hourly":        hourly_scores,
        "bestWindows":   best_windows,
        "sunriseHour":   sunrise_hour_decimal,
        "sunsetHour":    sunset_hour_decimal,
        "moon":          moon,
        "wind":          wind,
        "elevationFt":   elev,
        "zone":          zone,
        "season":        current_season,
        "isToday":       is_today,
        "dayLabel":      day_label,
    }
