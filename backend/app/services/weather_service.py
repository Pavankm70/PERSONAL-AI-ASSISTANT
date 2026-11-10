import httpx
from typing import Dict, Any, Optional

# Weather code mapping according to WMO code standards
WMO_WEATHER_CODES = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}

class WeatherService:
    """
    Real meteorological weather telemetry service powered by Open-Meteo.
    Requires no proprietary API key and provides live global forecast data.
    """
    async def get_weather(self, city: str = "Bengaluru") -> Dict[str, Any]:
        city_clean = city.strip()
        if not city_clean:
            city_clean = "Bengaluru"

        async with httpx.AsyncClient(timeout=12.0) as client:
            # 1. Geocode city name to latitude & longitude
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_res = await client.get(geo_url, params={"name": city_clean, "count": 1, "language": "en", "format": "json"})
            if geo_res.status_code != 200:
                return {
                    "status": "error",
                    "city": city_clean,
                    "message": f"Geocoding service unavailable (status {geo_res.status_code})."
                }

            geo_data = geo_res.json()
            results = geo_data.get("results", [])
            if not results:
                return {
                    "status": "not_found",
                    "city": city_clean,
                    "message": f"Could not find coordinates for location '{city_clean}'."
                }

            loc = results[0]
            lat = loc["latitude"]
            lon = loc["longitude"]
            location_name = f"{loc.get('name')}, {loc.get('admin1', '')} {loc.get('country', '')}".strip()

            # 2. Query Open-Meteo Forecast
            weather_url = "https://api.open-meteo.com/v1/forecast"
            params = {
                "latitude": lat,
                "longitude": lon,
                "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,weather_code,wind_speed_10m",
                "timezone": "auto"
            }
            weather_res = await client.get(weather_url, params=params)
            if weather_res.status_code != 200:
                return {
                    "status": "error",
                    "city": location_name,
                    "message": "Weather forecast service temporarily unavailable."
                }

            w_data = weather_res.json()
            curr = w_data.get("current", {})
            w_code = curr.get("weather_code", 0)
            condition = WMO_WEATHER_CODES.get(w_code, "Fair")

            return {
                "status": "success",
                "location": location_name,
                "coordinates": {"lat": lat, "lon": lon},
                "temperatureC": curr.get("temperature_2m"),
                "apparentTemperatureC": curr.get("apparent_temperature"),
                "humidityPercent": curr.get("relative_humidity_2m"),
                "windSpeedKmh": curr.get("wind_speed_10m"),
                "precipitationMm": curr.get("precipitation"),
                "condition": condition,
                "weatherCode": w_code,
                "time": curr.get("time")
            }

weather_service = WeatherService()
