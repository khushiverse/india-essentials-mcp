import asyncio

import httpx

from india_essentials_mcp import server


def run(coro):
    return asyncio.run(coro)


def test_aqi_category_bands():
    assert server.aqi_category(30) == "Good"
    assert server.aqi_category(100) == "Moderate"
    assert server.aqi_category(180) == "Unhealthy"
    assert server.aqi_category(450) == "Hazardous"
    assert server.aqi_category(None) == "Unknown"


def test_ifsc_rejects_bad_format():
    assert "error" in run(server.lookup_ifsc("nope"))


def test_ifsc_success(monkeypatch):
    async def fake(url, **params):
        return {"IFSC": "HDFC0000001", "BANK": "HDFC Bank", "BRANCH": "Mumbai",
                "UPI": True, "NEFT": True, "IMPS": True, "RTGS": True}
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.lookup_ifsc(" hdfc0000001 "))
    assert out["bank"] == "HDFC Bank"
    assert out["supports"]["upi"] is True


def test_ifsc_not_found(monkeypatch):
    async def fake(url, **params):
        req = httpx.Request("GET", url)
        raise httpx.HTTPStatusError("nf", request=req, response=httpx.Response(404, request=req))
    monkeypatch.setattr(server, "_get_json", fake)
    assert "not found" in run(server.lookup_ifsc("HDFC0000001"))["error"]


def test_pincode_rejects_bad_format():
    assert "error" in run(server.lookup_pincode("012345"))


def test_pincode_success(monkeypatch):
    async def fake(url, **params):
        return [{"Status": "Success", "PostOffice": [
            {"Name": "Bangalore GPO", "BranchType": "Head Post Office",
             "DeliveryStatus": "Delivery", "District": "Bengaluru", "State": "Karnataka"}]}]
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.lookup_pincode("560001"))
    assert out["state"] == "Karnataka"
    assert out["post_offices"][0]["name"] == "Bangalore GPO"


def test_pincode_not_found(monkeypatch):
    async def fake(url, **params):
        return [{"Status": "Error", "PostOffice": None}]
    monkeypatch.setattr(server, "_get_json", fake)
    assert "error" in run(server.lookup_pincode("999999"))


def test_air_quality_success(monkeypatch):
    async def fake(url, **params):
        if "geocoding" in url:
            return {"results": [{"name": "Bengaluru", "admin1": "Karnataka",
                                 "latitude": 12.97, "longitude": 77.59}]}
        return {"current": {"time": "2026-11-02T12:00", "us_aqi": 85, "pm2_5": 25.0},
                "current_units": {"pm2_5": "μg/m³"}}
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.get_air_quality("Bengaluru"))
    assert out["category"] == "Moderate"
    assert out["pollutants"]["pm2_5"]["unit"] == "μg/m³"


def test_air_quality_unknown_city(monkeypatch):
    async def fake(url, **params):
        return {}
    monkeypatch.setattr(server, "_get_json", fake)
    assert "error" in run(server.get_air_quality("Atlantis"))


# ---- new: aqi_by_pincode and caching ----

def test_aqi_by_pincode_success(monkeypatch):
    async def fake(url, **params):
        if "postalpincode" in url:
            return [{"Status": "Success", "PostOffice": [
                {"Name": "Bangalore GPO", "District": "Bengaluru", "State": "Karnataka"}]}]
        if "geocoding" in url:
            return {"results": [
                {"name": "Bengaluru", "admin1": "Maharashtra", "latitude": 1.0, "longitude": 1.0},
                {"name": "Bengaluru", "admin1": "Karnataka", "latitude": 12.97, "longitude": 77.59}]}
        return {"current": {"time": "t", "us_aqi": 160}, "current_units": {}}
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.aqi_by_pincode("560001"))
    assert out["pincode"] == "560001"
    assert out["matched_area"] == "Bengaluru, Karnataka"
    assert out["location"]["latitude"] == 12.97  # state filter picked Karnataka
    assert out["category"] == "Unhealthy"


def test_aqi_by_pincode_bad_input():
    assert "error" in run(server.aqi_by_pincode("abc"))


def test_aqi_by_pincode_unknown_pin(monkeypatch):
    async def fake(url, **params):
        return [{"Status": "Error", "PostOffice": None}]
    monkeypatch.setattr(server, "_get_json", fake)
    assert "error" in run(server.aqi_by_pincode("999999"))


def test_cache_avoids_second_request():
    server._cache.clear()
    calls = []

    def handler(request):
        calls.append(request.url)
        return httpx.Response(200, json={"IFSC": "HDFC0000001", "BANK": "HDFC Bank"})

    server._transport = httpx.MockTransport(handler)
    try:
        run(server.lookup_ifsc("HDFC0000001"))
        run(server.lookup_ifsc("HDFC0000001"))
    finally:
        server._transport = None
        server._cache.clear()
    assert len(calls) == 1


def test_errors_are_not_cached():
    server._cache.clear()
    calls = []

    def handler(request):
        calls.append(1)
        return httpx.Response(500)

    server._transport = httpx.MockTransport(handler)
    try:
        run(server.lookup_ifsc("HDFC0000001"))
        run(server.lookup_ifsc("HDFC0000001"))
    finally:
        server._transport = None
        server._cache.clear()
    assert len(calls) == 2


# ---- name matching ----

def test_city_alias_applied(monkeypatch):
    seen = []

    async def fake(url, **params):
        if "geocoding" in url:
            seen.append(params["name"])
            return {"results": [{"name": "Bengaluru", "admin1": "Karnataka",
                                 "latitude": 12.97, "longitude": 77.59}]}
        return {"current": {"us_aqi": 40}, "current_units": {}}
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.get_air_quality("Bangalore"))
    assert seen == ["Bengaluru"]
    assert out["category"] == "Good"


def test_pincode_tries_office_name_when_district_fails(monkeypatch):
    async def fake(url, **params):
        if "postalpincode" in url:
            return [{"Status": "Success", "PostOffice": [
                {"Name": "Weirdtown GPO", "District": "Unknownshire", "State": "Karnataka"}]}]
        if "geocoding" in url:
            if params["name"] == "Weirdtown":
                return {"results": [{"name": "Weirdtown", "admin1": "Karnataka",
                                     "latitude": 1.0, "longitude": 2.0}]}
            return {}
        return {"current": {"us_aqi": 120}, "current_units": {}}
    monkeypatch.setattr(server, "_get_json", fake)
    out = run(server.aqi_by_pincode("560001"))
    assert out["location"]["name"] == "Weirdtown"
    assert "warning" not in out


def test_pincode_warns_when_state_mismatch(monkeypatch):
    async def fake(url, **params):
        if "postalpincode" in url:
            return [{"Status": "Success", "PostOffice": [
                {"Name": "X", "District": "Foo", "State": "Karnataka"}]}]
        if "geocoding" in url:
            return {"results": [{"name": "Foo", "admin1": "Goa", "latitude": 1.0, "longitude": 2.0}]}
        return {"current": {"us_aqi": 10}, "current_units": {}}
    monkeypatch.setattr(server, "_get_json", fake)
    assert "warning" in run(server.aqi_by_pincode("560001"))


def test_place_candidates_cleaning():
    offices = [{"Name": "Bangalore GPO", "District": "Central Delhi"}]
    assert server._place_candidates(offices) == ["Central Delhi", "Delhi", "Bangalore"]
