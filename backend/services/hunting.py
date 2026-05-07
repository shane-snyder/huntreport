"""
Whitetail movement-prediction engine.

Single species. The headline output is a 0-100 "movement index" per hour
(rendered as a percentage in the UI) that combines time-of-day, temperature,
barometric trend, wind, moon, and proximity to peak rut.

We do not claim this is a calibrated probability. It's a deterministic
heuristic anchored on classic whitetail-movement triggers, weighted to
let you compare days and hours against each other.
"""

from datetime import datetime, timedelta, date
import math

# ── Rut timing by latitude (US/Canada) ──────────────────────────────────
# Approximate peak-breeding date. Whitetail rut is photoperiod-driven, so
# the peak in a given latitude band is consistent year-to-year within ~5
# days, regardless of weather.

def _rut_peak_date(year: int, lat: float) -> date:
    if lat >= 43:
        m, d = 11, 8
    elif lat >= 38:
        m, d = 11, 13
    elif lat >= 33:
        m, d = 11, 18
    elif lat >= 30:
        m, d = 12, 1
    else:
        m, d = 12, 20
    return date(year, m, d)


def whitetail_phase(d: date, lat: float) -> dict:
    """Return phase label + a 0..1 'rut intensity' for a given date.

    Intensity drives how much the hourly score weights mid-day movement
    (high during peak rut, low in summer).
    """
    # Pick the rut peak nearest to the given date — handle dates in early
    # year (Jan-Feb) by checking previous year's peak too.
    candidates = [_rut_peak_date(d.year - 1, lat),
                  _rut_peak_date(d.year, lat),
                  _rut_peak_date(d.year + 1, lat)]
    peak = min(candidates, key=lambda p: abs((d - p).days))
    delta = (d - peak).days

    if -7 <= delta <= 7:
        return {"phase": "peak_rut",     "label": "PEAK RUT",     "intensity": 1.00, "daysFromPeak": delta}
    if -21 <= delta < -7:
        return {"phase": "pre_rut",      "label": "PRE-RUT",      "intensity": 0.85, "daysFromPeak": delta}
    if 7 < delta <= 21:
        return {"phase": "post_rut",     "label": "POST-RUT",     "intensity": 0.55, "daysFromPeak": delta}
    if 21 < delta <= 60:
        return {"phase": "late_season",  "label": "LATE SEASON",  "intensity": 0.45, "daysFromPeak": delta}
    if -60 <= delta < -21:
        return {"phase": "early_season", "label": "EARLY SEASON", "intensity": 0.35, "daysFromPeak": delta}
    return {"phase": "off_season",   "label": "OFF-SEASON",   "intensity": 0.15, "daysFromPeak": delta}


# ── Hourly scoring ──────────────────────────────────────────────────────

def compute_hourly_score(
    hour: int,
    temp_f: float | None,
    temp_delta_24h: float | None,
    wind_mph: float | None,
    cloud_pct: float | None,
    pressure: float | None,
    pressure_delta_24h: float | None,
    pressure_delta_12h: float | None,
    pressure_delta_6h: float | None,
    pressure_drop_pre: float | None,    # ΔP from (now-24h) to (now-12h) — the "before" leg of a front cycle
    pressure_rise_post: float | None,   # ΔP from (now-12h) to now — the "after" leg of a front cycle
    precip_mm: float | None,
    moon_illum: float,
    is_daylight: bool,
    near_dawn: bool,
    near_dusk: bool,
    rut_intensity: float,
) -> tuple[int, list[str]]:
    s = 50
    factors: list[str] = []

    # ── Time of day ─────────────────────────────────────────────────
    if near_dawn:
        s += 22
        factors.append("dawn")
    elif near_dusk:
        s += 20
        factors.append("dusk")
    elif is_daylight:
        if 11 <= hour <= 14:
            midday = -10 + int(15 * rut_intensity)
            s += midday
            if midday < 0:
                factors.append("midday lull")
            elif midday > 0:
                factors.append("rut cruising")
        else:
            s += 2
    else:
        s -= 6

    # ── Temperature: absolute window + 24h change ───────────────────
    # Per HuntWise pros: relative change matters more than absolute. Score
    # absolute first (deer have a thermal preference), then layer the 24h
    # trend on top so a 50°F day after 70°F yesterday outscores a 50°F day
    # after 35°F yesterday.
    if temp_f is not None:
        if 25 <= temp_f <= 50:
            s += 12
            factors.append("cool temps")
        elif 50 < temp_f <= 60:
            s += 5
        elif 15 <= temp_f < 25:
            s += 5
            factors.append("cold push")
        elif temp_f < 5:
            s -= 12
            factors.append("brutal cold")
        elif temp_f > 75:
            s -= 12
            factors.append("warm hold")
        elif temp_f > 65:
            s -= 3

    if temp_delta_24h is not None:
        if temp_delta_24h <= -15:
            s += 10
            factors.append("major cool-down")
        elif temp_delta_24h <= -8:
            s += 6
            factors.append("cooling trend")
        elif temp_delta_24h <= -4:
            s += 3
        elif temp_delta_24h >= 15:
            s -= 8
            factors.append("major warm-up")
        elif temp_delta_24h >= 8:
            s -= 5
            factors.append("warming trend")
        elif temp_delta_24h >= 4:
            s -= 2

    # ── Wind ─────────────────────────────────────────────────────────
    if wind_mph is not None:
        if 3 <= wind_mph <= 10:
            s += 10
            factors.append("steady wind")
        elif wind_mph < 3:
            s += 0
        elif wind_mph < 15:
            s -= 2
        elif wind_mph < 22:
            s -= 12
            factors.append("strong wind")
        else:
            s -= 20
            factors.append("gale")

    # ── Pressure: cycle detection, then magnitude tiers ─────────────
    # The strongest deer-movement signal is the post-front recovery
    # window: pressure dropped 5+ hPa in the 12-24h prior to "now", then
    # rose 2+ hPa in the last 12h. Literature consistently flags the
    # 24-48h *after* a front passes as the canonical hunt.
    cycle_handled = False
    if pressure_drop_pre is not None and pressure_rise_post is not None:
        if pressure_drop_pre <= -8 and pressure_rise_post >= 4:
            s += 18
            factors.append("post-front prime")
            cycle_handled = True
        elif pressure_drop_pre <= -5 and pressure_rise_post >= 2:
            s += 14
            factors.append("post-front window")
            cycle_handled = True

    if not cycle_handled:
        # Falling tiers — magnitude based on the 4-5 tenths inHg threshold
        # the literature pegs as max-activity (≈13-17 hPa / 24h).
        if pressure_delta_24h is not None and pressure_delta_24h <= -13:
            s += 12
            factors.append("major front")
        elif pressure_delta_6h is not None and pressure_delta_6h <= -8:
            s += 14
            factors.append("strong front edge")
        elif pressure_delta_6h is not None and pressure_delta_6h <= -5:
            s += 10
            factors.append("front edge")
        elif pressure_delta_6h is not None and pressure_delta_6h <= -2:
            s += 5
            factors.append("falling fast")

        # Rising tiers — post-front recovery without the full cycle pattern
        if pressure_delta_24h is not None:
            if pressure_delta_24h >= 8:
                s += 12
                factors.append("strong recovery")
            elif pressure_delta_24h >= 5 and pressure is not None and pressure >= 1015:
                s += 10
                factors.append("rising into high")
            elif pressure_delta_24h >= 2:
                s += 5
                factors.append("rising barometer")
            elif pressure_delta_24h <= -5:
                # Falling but not in a recognizable front pattern
                s -= 4
                factors.append("falling pressure")
            elif -1 <= pressure_delta_24h <= 1 and pressure is not None:
                if pressure >= 1020:
                    s += 5
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

    # ── Precipitation ────────────────────────────────────────────────
    if precip_mm is not None:
        if precip_mm > 2.5:
            s -= 14
            factors.append("heavy rain")
        elif precip_mm > 0.5:
            s -= 4
            factors.append("rain")

    # ── Moon ─────────────────────────────────────────────────────────
    if moon_illum > 0.85:
        penalty = int(7 * (1.2 - rut_intensity))
        s -= penalty
        factors.append("full-moon nocturnal")
    elif moon_illum < 0.15:
        s += 3
        factors.append("dark moon")

    return max(0, min(100, round(s))), factors


# ── Moon phase ───────────────────────────────────────────────────────────

def moon_phase(now: datetime) -> dict:
    ref = datetime(2000, 1, 6, 18, 14)
    days = (now - ref).total_seconds() / 86400.0
    cycle = 29.530588853
    phase = (days % cycle) / cycle

    illum = round((1 - math.cos(2 * math.pi * phase)) / 2, 2)

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

    return {
        "label":        label,
        "icon":         icon,
        "illumination": illum,
        "phaseFrac":    round(phase, 3),
    }


# ── Wind helper ──────────────────────────────────────────────────────────

_COMPASS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
            "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]


def wind_compass(deg: float | None) -> str:
    if deg is None:
        return "—"
    return _COMPASS[int((deg % 360) / 22.5 + 0.5) % 16]


# ── Day scoring ──────────────────────────────────────────────────────────

def _parse_iso(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return None


def score_day(weather: dict, day_index: int, lat: float) -> dict:
    """Score every hour of one day. Returns a full day record."""
    daily  = weather.get("daily", {}) or {}
    hourly = weather.get("hourly", {}) or {}

    times    = hourly.get("time") or []
    h_temp   = hourly.get("temperature_2m") or []
    h_wind   = hourly.get("wind_speed_10m") or []
    h_wdir   = hourly.get("wind_direction_10m") or []
    h_gust   = hourly.get("wind_gusts_10m") or []
    h_cloud  = hourly.get("cloud_cover") or []
    h_press  = hourly.get("pressure_msl") or []
    h_precip = hourly.get("precipitation") or []
    h_isday  = hourly.get("is_day") or []

    day_dates = daily.get("time") or []
    if day_index >= len(day_dates):
        return {"hourly": [], "peakScore": 0, "peakHour": 0, "avgScore": 0,
                "sunriseHour": None, "sunsetHour": None}

    target_date_str = day_dates[day_index]
    target_date     = _parse_iso(target_date_str + "T00:00").date() if target_date_str else None

    sunrise_dt = _parse_iso((daily.get("sunrise") or [None] * 7)[day_index])
    sunset_dt  = _parse_iso((daily.get("sunset")  or [None] * 7)[day_index])

    # rut intensity for this specific calendar date
    phase = whitetail_phase(target_date, lat) if target_date else {"intensity": 0.5, "label": "—", "phase": "unknown", "daysFromPeak": 0}
    moon = moon_phase(datetime.combine(target_date, datetime.min.time())) if target_date else moon_phase(datetime.utcnow())

    # locate the day's hour-0 in the global hourly array
    day_start_idx = None
    for i, t in enumerate(times):
        if t.startswith(target_date_str):
            day_start_idx = i
            break
    if day_start_idx is None:
        return {"hourly": [], "peakScore": 0, "peakHour": 0, "avgScore": 0,
                "sunriseHour": None, "sunsetHour": None,
                "phase": phase, "moon": moon}

    hourly_out = []
    for offset in range(24):
        idx = day_start_idx + offset
        if idx >= len(times):
            break
        ts    = times[idx]
        hour  = int(ts.split("T")[1].split(":")[0]) if "T" in ts else offset
        ts_dt = _parse_iso(ts)

        temp_f   = h_temp[idx]   if idx < len(h_temp)   else None
        wind_mph = h_wind[idx]   if idx < len(h_wind)   else None
        wind_dir = h_wdir[idx]   if idx < len(h_wdir)   else None
        gust     = h_gust[idx]   if idx < len(h_gust)   else None
        cloud    = h_cloud[idx]  if idx < len(h_cloud)  else None
        press    = h_press[idx]  if idx < len(h_press)  else None
        precip   = h_precip[idx] if idx < len(h_precip) else None
        is_day   = bool(h_isday[idx]) if idx < len(h_isday) else (6 <= hour <= 19)

        # ── Pressure deltas (for cycle detection + tiered magnitude scoring)
        def _delta(now_idx: int, back_h: int) -> float | None:
            if press is None or now_idx < back_h:
                return None
            past = h_press[now_idx - back_h] if now_idx - back_h < len(h_press) else None
            return None if past is None else press - past

        d24 = _delta(idx, 24)
        d12 = _delta(idx, 12)
        d6  = _delta(idx, 6)

        # Front-cycle legs: drop_pre = the slide from -24h to -12h, rise_post = the recovery from -12h to now
        drop_pre = None
        if idx >= 24 and idx - 12 < len(h_press):
            p24 = h_press[idx - 24] if idx - 24 < len(h_press) else None
            p12 = h_press[idx - 12] if idx - 12 < len(h_press) else None
            if p24 is not None and p12 is not None:
                drop_pre = p12 - p24
        rise_post = None
        if press is not None and idx >= 12:
            p12 = h_press[idx - 12] if idx - 12 < len(h_press) else None
            if p12 is not None:
                rise_post = press - p12

        # ── Temperature delta over the last 24 hours
        tD24 = None
        if temp_f is not None and idx >= 24 and idx - 24 < len(h_temp):
            past_t = h_temp[idx - 24]
            if past_t is not None:
                tD24 = temp_f - past_t

        near_dawn = bool(sunrise_dt and ts_dt and abs((ts_dt - sunrise_dt).total_seconds()) <= 5400)
        near_dusk = bool(sunset_dt  and ts_dt and abs((ts_dt - sunset_dt).total_seconds())  <= 5400)

        score, factors = compute_hourly_score(
            hour, temp_f, tD24, wind_mph, cloud, press,
            d24, d12, d6, drop_pre, rise_post,
            precip,
            moon["illumination"], is_day, near_dawn, near_dusk,
            phase["intensity"],
        )
        hourly_out.append({
            "hour":         hour,
            "score":        score,
            "factors":      factors,
            "tempF":        round(temp_f, 1) if temp_f is not None else None,
            "tempD24":      round(tD24, 1) if tD24 is not None else None,
            "windMph":      round(wind_mph, 1) if wind_mph is not None else None,
            "windDirDeg":   round(wind_dir, 0) if wind_dir is not None else None,
            "windCompass":  wind_compass(wind_dir),
            "gustMph":      round(gust, 1) if gust is not None else None,
            "cloudPct":     round(cloud, 0) if cloud is not None else None,
            "pressureHpa":  round(press, 1) if press is not None else None,
            "pressureD24":  round(d24, 1) if d24 is not None else None,
            "pressureD12":  round(d12, 1) if d12 is not None else None,
            "pressureD6":   round(d6, 1) if d6 is not None else None,
            "precipMm":     round(precip, 2) if precip is not None else None,
            "isDay":        is_day,
        })

    if not hourly_out:
        return {"hourly": [], "peakScore": 0, "peakHour": 0, "avgScore": 0,
                "sunriseHour": None, "sunsetHour": None,
                "phase": phase, "moon": moon}

    peak_h = max(hourly_out, key=lambda h: h["score"])
    daylight = [h["score"] for h in hourly_out if h["isDay"]]
    avg = round(sum(daylight) / len(daylight)) if daylight else round(sum(h["score"] for h in hourly_out) / len(hourly_out))

    sunrise_decimal = (sunrise_dt.hour + sunrise_dt.minute / 60) if sunrise_dt else None
    sunset_decimal  = (sunset_dt.hour  + sunset_dt.minute  / 60) if sunset_dt  else None

    return {
        "date":         target_date_str,
        "hourly":       hourly_out,
        "peakScore":    peak_h["score"],
        "peakHour":     peak_h["hour"],
        "peakFactors":  peak_h["factors"],
        "avgScore":     avg,
        "sunriseHour":  sunrise_decimal,
        "sunsetHour":   sunset_decimal,
        "tempMaxF":     (daily.get("temperature_2m_max") or [None] * 7)[day_index],
        "tempMinF":     (daily.get("temperature_2m_min") or [None] * 7)[day_index],
        "weatherCode":  (daily.get("weather_code")        or [None] * 7)[day_index],
        "phase":        phase,
        "moon":         moon,
    }


# ── Top-level entry point ───────────────────────────────────────────────

def build_hunting_analysis(
    lat: float,
    lon: float,
    name: str,
    weather: dict,
    terrain: dict,
    day_index: int = 0,
) -> dict:
    """Build a full whitetail report — the selected day plus a 7-day strip."""
    daily = weather.get("daily", {}) or {}
    n_days = len(daily.get("time") or [])
    n_days = min(n_days, 7)

    week = [score_day(weather, i, lat) for i in range(n_days)]
    if day_index >= len(week):
        day_index = 0
    selected = week[day_index] if week else {}

    # which day this week is best — peak score, tiebreak on average
    best_idx = 0
    best_key = (-1, -1)
    for i, d in enumerate(week):
        key = (d.get("peakScore", 0), d.get("avgScore", 0))
        if key > best_key:
            best_key = key
            best_idx = i

    weekly_summary = [{
        "dayIndex":    i,
        "date":        d.get("date"),
        "peakScore":   d.get("peakScore", 0),
        "peakHour":    d.get("peakHour", 0),
        "avgScore":    d.get("avgScore", 0),
        "tempMaxF":    d.get("tempMaxF"),
        "tempMinF":    d.get("tempMinF"),
        "weatherCode": d.get("weatherCode"),
        "phase":       d.get("phase", {}).get("phase"),
        "phaseLabel":  d.get("phase", {}).get("label"),
    } for i, d in enumerate(week)]

    elev = terrain.get("elevationFt") if isinstance(terrain, dict) else None
    zone = terrain.get("zone") if isinstance(terrain, dict) else None

    # Pull representative wind for the panel — prefer current hour today,
    # else the day's peak hour
    cur_hour = datetime.utcnow().hour
    is_today = day_index == 0
    ref = None
    if selected.get("hourly"):
        if is_today and 0 <= cur_hour < len(selected["hourly"]):
            ref = selected["hourly"][cur_hour]
        else:
            ref = max(selected["hourly"], key=lambda h: h["score"])

    wind = {
        "speedMph":     ref["windMph"]     if ref else None,
        "directionDeg": ref["windDirDeg"]  if ref else None,
        "compass":      ref["windCompass"] if ref else "—",
        "gustMph":      ref["gustMph"]     if ref else None,
    }

    return {
        "score":        selected.get("peakScore", 0),
        "peakHour":     selected.get("peakHour", 0),
        "avgScore":     selected.get("avgScore", 0),
        "peakFactors":  selected.get("peakFactors", []),
        "hourly":       selected.get("hourly", []),
        "sunriseHour":  selected.get("sunriseHour"),
        "sunsetHour":   selected.get("sunsetHour"),
        "weeklyForecast": weekly_summary,
        "bestDayIndex": best_idx,
        "phase":        selected.get("phase", {}),
        "moon":         selected.get("moon", {}),
        "wind":         wind,
        "elevationFt":  elev,
        "zone":         zone,
        "isToday":      is_today,
        "dayLabel":     selected.get("date") or "",
    }
