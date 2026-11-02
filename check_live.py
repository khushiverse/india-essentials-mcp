import asyncio, json
from india_essentials_mcp import server

async def main():
    checks = [
        ("IFSC", server.lookup_ifsc("SBIN0000001")),
        ("PIN", server.lookup_pincode("560001")),
        ("AQI city", server.get_air_quality("Bengaluru")),
        ("AQI by PIN", server.aqi_by_pincode("560001")),
    ]
    for label, coro in checks:
        print("=====", label)
        print(json.dumps(await coro, indent=2, ensure_ascii=False))

asyncio.run(main())
