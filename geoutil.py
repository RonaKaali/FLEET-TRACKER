# geoutil.py (extended)
# ------------------------------------------------------------
# Helper utilities for geolocation.
#   - get_location_by_ip()          : IP based location via geocoder.
#   - get_location_by_wifi(access_points) : Wi‑Fi based location using Google Geolocation API (requires API key).
#   - reverse_geocode(lat, lon)    : Convert coordinates to a human readable address.
# ------------------------------------------------------------
import time
import requests
import geocoder
from config import NOMINATIM_URL, USER_AGENT, API_DELAY_MS, GOOGLE_GEO_API_KEY

_last_api_call = 0  # timestamp of last external request (epoch seconds)


def _respect_rate_limit():
    """Ensure we respect the configured API delay between calls.
    This helps avoid hitting rate limits of public services.
    """
    global _last_api_call
    now = time.time()
    elapsed_ms = (now - _last_api_call) * 1000
    if elapsed_ms < API_DELAY_MS:
        time.sleep((API_DELAY_MS - elapsed_ms) / 1000.0)
    _last_api_call = time.time()


def get_location_by_ip():
    """Return (lat, lon) using the public IP address.
    Uses the `geocoder` library which queries a free service.
    Raises RuntimeError if the service fails.
    """
    g = geocoder.ip('me')
    if g.ok and g.latlng:
        return g.latlng
    raise RuntimeError("Unable to obtain location from IP.")


def get_location_by_wifi(access_points):
    """Return (lat, lon) based on nearby Wi‑Fi access points.

    Parameters
    ----------
    access_points : list[dict]
        Each dict must contain at least:
            - "mac"   : MAC address string (e.g. "00:25:9c:cf:1c:ac")
            - "signal": Signal strength in dBm (negative integer)
        Optional fields: "age", "channel", "snr".

    Returns
    -------
    tuple[float, float]
        (latitude, longitude)

    Notes
    -----
    The function calls Google's Geolocation API (https://www.googleapis.com/geolocation/v1/geolocate).
    You need a valid API key stored in `GOOGLE_GEO_API_KEY` in `config.py`.
    If the request fails (network error, HTTP error, or API returns no location), the function will raise
    `RuntimeError`. Callers should catch this and optionally fall back to IP‑based location.
    """
    if not isinstance(access_points, list) or not access_points:
        raise ValueError("access_points must be a non‑empty list of dicts.")

    # Build payload according to Google Geolocation API specification
    payload = {
        "wifiAccessPoints": [
            {
                "macAddress": ap["mac"],
                "signalStrength": ap.get("signal", -50),
                # Optional fields – include if present
                **{k: v for k, v in ap.items() if k not in {"mac", "signal"}}
            }
            for ap in access_points
        ]
    }

    url = f"https://www.googleapis.com/geolocation/v1/geolocate?key={GOOGLE_GEO_API_KEY}"
    headers = {"Content-Type": "application/json"}
    try:
        _respect_rate_limit()
        response = requests.post(url, json=payload, headers=headers, timeout=8)
        response.raise_for_status()
        data = response.json()
        location = data.get("location")
        if location and "lat" in location and "lng" in location:
            return (location["lat"], location["lng"])
        raise RuntimeError("Geolocation API did not return a location.")
    except requests.RequestException as e:
        raise RuntimeError(f"WiFi geolocation request failed: {e}")


def reverse_geocode(lat, lon):
    """Convert latitude/longitude to a human‑readable address using Nominatim.
    Returns a string address or ``None`` on failure.
    """
    _respect_rate_limit()
    params = {
        "format": "json",
        "lat": lat,
        "lon": lon,
        "zoom": 18,
        "addressdetails": 1,
    }
    headers = {"User-Agent": USER_AGENT}
    try:
        resp = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("display_name")
    except requests.RequestException:
        pass
    return None
