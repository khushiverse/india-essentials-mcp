# Publishing checklist

Replace `khushiverse` (LICENSE, pyproject.toml) and `khushiverse` (README, pyproject.toml) first.

## 1. Put it on GitHub
```bash
cd india-essentials-mcp
git init && git add . && git commit -m "Initial release"
git branch -M main
# create an empty repo named india-essentials-mcp on github.com, then:
git remote add origin https://github.com/khushiverse/india-essentials-mcp.git
git push -u origin main
```
Add repo topics: `mcp`, `mcp-server`, `india`, `ai-agents`, `python`.

## 2. Record a demo GIF (do this before launching)
Connect the server to Claude Desktop, ask "Which bank is IFSC SBIN0000001 and what's the air quality at PIN 560001?",
and record ~10 seconds with ScreenToGif (Windows), Kap (Mac) or peek (Linux).
Save as `demo.gif`, then put `![demo](demo.gif)` under the title in README.md.

## 3. Publish to PyPI (trusted publishing, no token)
1. Create an account at pypi.org.
2. PyPI → Your projects → Publishing → "Add a pending publisher":
   project `india-essentials-mcp`, owner = your GitHub username, repo `india-essentials-mcp`,
   workflow `publish.yml`, environment `pypi`.
3. On GitHub: Settings → Environments → New environment named `pypi`.
4. On GitHub: Releases → Draft a new release → tag `v0.2.0` → Publish.
   The workflow builds and uploads automatically.
5. Test: `uvx india-essentials-mcp`

(If the name is taken on PyPI, change `name` in pyproject.toml.)

## 4. Get it discovered
- Open a PR adding it to the community MCP server lists (search GitHub for "awesome-mcp-servers").
- Post on Reddit (r/mcp, r/LocalLLaMA, r/developersIndia), X, LinkedIn, and Hacker News ("Show HN").
- Lead with the demo GIF and the one-line pitch: "Ask your AI about IFSC, PIN codes and AQI in India. No API keys."
- Reply to every issue and star in the first week.
