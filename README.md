# India Essentials MCP

[![CI](https://github.com/khushiverse/india-essentials-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/khushiverse/india-essentials-mcp/actions)

An [MCP](https://modelcontextprotocol.io) server that gives AI assistants everyday Indian lookups: bank IFSC codes, PIN codes and air quality. No API keys needed.

| Tool | What it does | Data source |
|------|--------------|-------------|
| `lookup_ifsc` | Bank, branch, address, MICR and UPI/NEFT/IMPS/RTGS support for an IFSC code | Razorpay IFSC API |
| `lookup_pincode` | Post offices, district and state for a 6-digit PIN code | India Post (postalpincode.in) |
| `get_air_quality` | Current AQI and pollutants for an Indian city | Open-Meteo |
| `aqi_by_pincode` | Current AQI for the area of a PIN code (PIN → district → AQI) | India Post + Open-Meteo |

Try asking your assistant:
- "Which bank and branch is IFSC SBIN0000001, and does it support UPI?"
- "What area is PIN code 560001?"
- "Is it safe to go for a run in Delhi right now?"
- "How is the air quality at PIN code 400001?"

## Install

```bash
# easiest (no install step)
uvx india-essentials-mcp

# or with pip
pip install india-essentials-mcp
```

## Connect to Claude Desktop

Add this to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "india-essentials": {
      "command": "uvx",
      "args": ["india-essentials-mcp"]
    }
  }
}
```

Restart Claude Desktop and the tools will appear.

## Develop

```bash
pip install -e ".[dev]"
pytest
npx @modelcontextprotocol/inspector india-essentials-mcp   # try tools in a browser UI
```

## Notes

- Air quality is modelled data on the US AQI scale, **not** an official CPCB ground-station reading.
- `aqi_by_pincode` is district-level, not street-level.
- Data comes from free third-party services, which may rate-limit or change.

## Roadmap

- [x] `aqi_by_pincode` (combine PIN lookup with air quality)
- [ ] GSTIN format validation
- [x] Caching to be kind to the free APIs (24h for IFSC/PIN, 15 min for AQI)
- [ ] CPCB station-level AQI

## License

MIT
