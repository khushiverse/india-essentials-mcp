"""India Essentials MCP server.

Tools:
  - lookup_ifsc:       bank branch details from an IFSC code
  - lookup_pincode:    post offices for a 6-digit PIN code
  - get_air_quality:   current air quality for an Indian city
  - aqi_by_pincode:    current air quality for the area of a PIN code

All data sources are free and need no API key.
"""
from __future__ import annotations

import re
import time
from typing import Any

import httpx
from mcp.server.mcpserver import MCPServer

mcp = MCPServer("india-essentials")

IFSC_URL = "https://ifsc.razorpay.com/{code}"
PIN_URL = "https://api.postalpincode.in/pincode/{pin}"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
AQ_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"

TIMEOUT = 10.0
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
PIN_RE = re.compile(r"^[1-9][0-9]{5}$")

# Cache lifetimes (seconds). Bank/postal data barely changes; air quality does.
TTL_STATIC = 24 * 60 * 60
TTL_AIR = 15 * 60

# US AQI bands (the scale Open-Meteo reports). CPCB's Indian scale differs.
AQI_BANDS = [
    (50, "Good"),
    (100, "Moderate"),
    (150, "Unhealthy for sensitive groups"),
    (200, "Unhealthy"),
    (300, "Very unhealthy"),
]

_cache: dict[tuple, tuple[float, Any]] = {}
_transport: httpx.AsyncBaseTransport | None = None  # overridden in tests


def aqi_category(aqi: float | int | None) -> str:
    """Map a US AQI value to its category label."""
    if aqi is None:
        return "Unknown"
    for upper, label in AQI_BANDS:
        if aqi <= upper:
            return label
    return "Hazardous"


async def _get_json(url: str, *, ttl: int = 0, **params: Any) -> Any:
    """GET a URL and return parsed JSON, with an optional in-memory TTL cache.

    Only successful responses are cached. Raises httpx errors on failure.
    """
    key = (url, tuple(sorted(params.items())))
    if ttl:
        hit = _cache.get(key)
        if hit and hit[0] > time.monotonic():
            return hit[1]
    async with httpx.AsyncClient(timeout=TIMEOUT, transport=_transport) as client:
        resp = await client.get(url, params=params or None)
        resp.raise_for_status()
        data = resp.json()
    if ttl:
        _cache[key] = (time.monotonic() + ttl, data)
    return data


# Old/colonial or variant city names -> the names the geocoder knows.
CITY_ALIASES = {
    "bangalore": "Bengaluru",
    "bombay": "Mumbai",
    "calcutta": "Kolkata",
    "madras": "Chennai",
    "poona": "Pune",
    "baroda": "Vadodara",
    "trivandrum": "Thiruvananthapuram",
    "cochin": "Kochi",
    "mysore": "Mysuru",
    "mangalore": "Mangaluru",
    "gurgaon": "Gurugram",
    "allahabad": "Prayagraj",
    "benares": "Varanasi",
    "banaras": "Varanasi",
    "vizag": "Visakhapatnam",
}
_QUALIFIERS = re.compile(r"\b(urban|rural|city|central|north|south|east|west|district)\b", re.I)
_OFFICE_SUFFIX = re.compile(r"\s+(GPO|HO|SO|BO|S\.O\.?|H\.O\.?|B\.O\.?)\s*$", re.I)


async def _geocode(name: str) -> list[dict]:
    """Geocode a place name in India (applies city-name aliases). Returns raw matches."""
    query = CITY_ALIASES.get(name.strip().lower(), name.strip())
    geo = await _get_json(
        GEOCODE_URL, ttl=TTL_STATIC, name=query, count=10, language="en", countryCode="IN"
    )
    return geo.get("results") or []


async def _find_place(name: str, state: str | None = None) -> dict | None:
    """Geocode a place name in India. Prefer a match in `state` when given."""
    results = await _geocode(name)
    if not results:
        return None
    if state:
        for r in results:
            if (r.get("admin1") or "").lower() == state.lower():
                return r
    return results[0]


def _place_candidates(offices: list[dict]) -> list[str]:
    """Name variants to try when locating a PIN: district, cleaned district, post-office names."""
    names: list[str] = []

    def add(n: str | None) -> None:
        n = re.sub(r"\s+", " ", (n or "").strip())
        if n and n.lower() not in {x.lower() for x in names}:
            names.append(n)

    district = (offices[0].get("District") or "").strip()
    add(district)
    add(_QUALIFIERS.sub("", district))
    for o in offices[:3]:
        add(_OFFICE_SUFFIX.sub("", (o.get("Name") or "").strip()))
    return names[:8]


async def _locate(candidates: list[str], state: str | None) -> tuple[dict | None, bool]:
    """Try each candidate name. Returns (place, state_matched). Prefers a result in `state`."""
    fallback = None
    for name in candidates:
        results = await _geocode(name)
        if state:
            for r in results:
                if (r.get("admin1") or "").lower() == state.lower():
                    return r, True
        if results and fallback is None:
            fallback = results[0]
    return fallback, False


async def _air_quality_at(place: dict) -> dict:
    aq = await _get_json(
        AQ_URL,
        ttl=TTL_AIR,
        latitude=place["latitude"],
        longitude=place["longitude"],
        current="us_aqi,pm2_5,pm10,carbon_monoxide,nitrogen_dioxide,sulphur_dioxide,ozone",
        timezone="auto",
    )
    current = aq.get("current", {})
    units = aq.get("current_units", {})
    aqi = current.get("us_aqi")
    return {
        "location": {
            "name": place.get("name"),
            "state": place.get("admin1"),
            "latitude": place["latitude"],
            "longitude": place["longitude"],
        },
        "time": current.get("time"),
        "aqi_us": aqi,
        "category": aqi_category(aqi),
        "pollutants": {
            key: {"value": current.get(key), "unit": units.get(key)}
            for key in ("pm2_5", "pm10", "carbon_monoxide", "nitrogen_dioxide", "sulphur_dioxide", "ozone")
        },
        "note": "US AQI scale from modelled data (Open-Meteo). Not the official CPCB reading.",
    }


@mcp.tool()
async def lookup_ifsc(ifsc: str) -> dict:
    """Get bank branch details (bank, branch, address, MICR, UPI/NEFT/IMPS/RTGS support)
    for an 11-character IFSC code such as 'HDFC0000001'."""
    code = ifsc.strip().upper()
    if not IFSC_RE.match(code):
        return {"error": "Invalid IFSC format. Expected 4 letters, a 0, then 6 letters/digits (e.g. HDFC0000001)."}
    try:
        data = await _get_json(IFSC_URL.format(code=code), ttl=TTL_STATIC)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"IFSC code {code} was not found."}
        return {"error": f"IFSC service returned HTTP {e.response.status_code}."}
    except httpx.HTTPError:
        return {"error": "Could not reach the IFSC service. Try again later."}
    return {
        "ifsc": data.get("IFSC"),
        "bank": data.get("BANK"),
        "branch": data.get("BRANCH"),
        "address": data.get("ADDRESS"),
        "city": data.get("CITY"),
        "district": data.get("DISTRICT"),
        "state": data.get("STATE"),
        "micr": data.get("MICR"),
        "contact": data.get("CONTACT"),
        "swift": data.get("SWIFT"),
        "supports": {
            "upi": data.get("UPI"),
            "neft": data.get("NEFT"),
            "imps": data.get("IMPS"),
            "rtgs": data.get("RTGS"),
        },
    }


async def _pin_offices(pin: str) -> list[dict] | None:
    """Return the raw post-office list for a PIN, or None if the PIN has no match."""
    data = await _get_json(PIN_URL.format(pin=pin), ttl=TTL_STATIC)
    entry = data[0] if isinstance(data, list) and data else {}
    offices = entry.get("PostOffice")
    if entry.get("Status") != "Success" or not offices:
        return None
    return offices


@mcp.tool()
async def lookup_pincode(pincode: str) -> dict:
    """List the post offices, district and state for a 6-digit Indian PIN code."""
    pin = pincode.strip()
    if not PIN_RE.match(pin):
        return {"error": "Invalid PIN code. Expected 6 digits, not starting with 0."}
    try:
        offices = await _pin_offices(pin)
    except httpx.HTTPError:
        return {"error": "Could not reach the PIN code service. Try again later."}
    if not offices:
        return {"error": f"No post offices found for PIN code {pin}."}
    return {
        "pincode": pin,
        "district": offices[0].get("District"),
        "state": offices[0].get("State"),
        "post_offices": [
            {"name": o.get("Name"), "type": o.get("BranchType"), "delivery": o.get("DeliveryStatus")}
            for o in offices
        ],
    }


@mcp.tool()
async def get_air_quality(city: str) -> dict:
    """Get current air quality (AQI and pollutant levels) for an Indian city,
    e.g. 'Bengaluru' or 'Delhi'. Values are modelled estimates, not a ground-station reading."""
    name = city.strip()
    if not name:
        return {"error": "Please provide a city name."}
    try:
        place = await _find_place(name)
        if not place:
            return {"error": f"Could not find a city called '{name}' in India."}
        return await _air_quality_at(place)
    except httpx.HTTPError:
        return {"error": "Could not reach the air quality service. Try again later."}


@mcp.tool()
async def aqi_by_pincode(pincode: str) -> dict:
    """Get current air quality for the area covered by a 6-digit Indian PIN code
    (for example '110001' for central Delhi). Uses the PIN's district to locate it,
    so the result is district-level, not street-level."""
    pin = pincode.strip()
    if not PIN_RE.match(pin):
        return {"error": "Invalid PIN code. Expected 6 digits, not starting with 0."}
    try:
        offices = await _pin_offices(pin)
        if not offices:
            return {"error": f"No post offices found for PIN code {pin}."}
        district, state = offices[0].get("District"), offices[0].get("State")
        place, exact = await _locate(_place_candidates(offices), state)
        if not place:
            return {"error": f"Found PIN {pin} ({district}, {state}) but could not locate it for air quality."}
        result = await _air_quality_at(place)
    except httpx.HTTPError:
        return {"error": "Could not reach a data service. Try again later."}
    result["pincode"] = pin
    result["matched_area"] = f"{district}, {state}"
    if not exact:
        result["warning"] = "Matched by place name only (state did not match), so the location may be approximate."
    return result


def main() -> None:
    mcp.run()  # stdio transport


if __name__ == "__main__":
    main()
