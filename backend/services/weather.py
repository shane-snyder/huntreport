import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current, hourly (with 24h of past data for pressure trend), and 7-day forecast.

    Hourly arrays are time-aligned: index 0 = 24 hours ago, index 24 = "now" hour,
    indexes 24..191 = next 7 days at hourly resolution. Use the `time` array to
    map indexes to wall-clock hours.
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "apparent_temperature",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "weather_code",
            "cloud_cover",
            "pressure_msl",
            "uv_index",
            "precipitation",
        ]),
        "hourly": ",".join([
            "temperature_2m",
            "relative_humidity_2m",
            "wind_speed_10m",
            "wind_direction_10m",
            "wind_gusts_10m",
            "cloud_cover",
            "pressure_msl",
            "precipitation",
            "is_day",
        ]),
        "daily": ",".join([
            "temperature_2m_max",
            "temperature_2m_min",
            "weather_code",
            "precipitation_sum",
            "wind_speed_10m_max",
            "wind_direction_10m_dominant",
            "uv_index_max",
            "precipitation_probability_max",
            "sunrise",
            "sunset",
        ]),
        "past_hours": 72,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 7,
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(OPEN_METEO_URL, params=params)
        if not resp.is_success:
            return {"error": f"Open-Meteo HTTP {resp.status_code}", "current": {}, "hourly": {}, "daily": {}}
        return resp.json()
