import threading
import time

import httpx
from PySide6.QtCore import QObject, Signal

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
REFRESH_SECONDS = 15 * 60
RETRY_SECONDS = 2 * 60
REQUEST_TIMEOUT = 10.0


def weather_glyph(code, is_day):
    # WMO weather interpretation codes, as returned by Open-Meteo.
    if code == 0:
        return "☀" if is_day else "☾"
    if code in (1, 2):
        return "⛅" if is_day else "☁"
    if code == 3 or code in (45, 48):
        return "☁"
    if code in (71, 73, 75, 77, 85, 86):
        return "❄"
    if code in (95, 96, 99):
        return "⚡"
    return "☂"


class WeatherProvider(QObject):
    changed = Signal(str, str)  # glyph, temperature text

    def __init__(self, city, language):
        super().__init__()
        self.city = city
        self.language = language
        threading.Thread(target=self._run, daemon=True).start()

    def _get(self, url, params):
        response = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT, trust_env=False)
        response.raise_for_status()
        return response.json()

    def _run(self):
        location = None
        while True:
            try:
                if location is None:
                    found = self._get(GEOCODING_URL, {"name": self.city, "count": 1, "language": self.language})
                    result = found["results"][0]
                    location = (result["latitude"], result["longitude"])
                data = self._get(FORECAST_URL, {
                    "latitude": location[0], "longitude": location[1],
                    "current": "temperature_2m,weather_code,is_day",
                })
                current = data["current"]
                self.changed.emit(
                    weather_glyph(current["weather_code"], current["is_day"]),
                    f"{round(current['temperature_2m'])}°",
                )
                time.sleep(REFRESH_SECONDS)
            except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
                time.sleep(RETRY_SECONDS)
