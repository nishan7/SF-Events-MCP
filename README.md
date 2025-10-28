# SF Rec Events MCP

A small FastMCP server and custom web widget for browsing upcoming San Francisco Recreation & Parks events. The Python service exposes an MCP tool (`search_sf_events`) over HTTP and serves an embeddable UI widget built with React/TypeScript.

## Features
- HTTP MCP server with `search_sf_events`
- Event filtering by dates, category, neighborhood, proximity, and free-text
- Embeddable results UI (cards + map view) compiled to a single widget
- Simple caching layer to reduce API calls

## Quickstart

### 1) Python environment
- `python -m venv .venv && source .venv/bin/activate`
- `python -m pip install -r requirements.txt`

Environment config:
- Copy/edit `env` and set `APPTOKEN` if you have your own Socrata app token. A development token is present in the repo's `env` file and used by default.

### 2) Build the web widget
- `cd web`
- `npm ci` (or `npm install`)
- `npm run build` (outputs `web/dist/component.js` and optional CSS)
- Optional dev loop: `npm run watch`

Note: the map view uses Mapbox GL. A public development token is embedded in `web/src/MapView.tsx`. For production, replace it with your own token.

### 3) Run the MCP server (HTTP)
From the repository root (after building the widget):

- `python -m uvicorn src.instacart_chatgpt.services.fastmcp_rec_events:app --reload --host 127.0.0.1 --port 8000`

The MCP endpoint is available at `http://127.0.0.1:8000/mcp`.

## Using the client
You can call the MCP server from Python using FastMCP's HTTP transport. Example:

```python
import asyncio
from fastmcp import Client

async def main():
    async with Client("http://127.0.0.1:8000/mcp") as client:
        result = await client.call_tool(
            name="search_sf_events",
            args={
                "limit": 5,
                "search": "music",
                "relative_date": "weekend",
            },
        )
        print(result.structured_content)

asyncio.run(main())
```

Tip: FastMCP also supports explicitly choosing the streamable HTTP transport when you need custom headers or auth.

```python
from fastmcp import Client
from fastmcp.client.transports import StreamableHttpTransport

transport = StreamableHttpTransport(url="http://127.0.0.1:8000/mcp")
async with Client(transport=transport) as client:
    await client.ping()
```

## Tools and resources
- Tool: `search_sf_events` — primary search endpoint with filters:
  - Arguments include `limit`, date range fields (`start_date_from`, `start_date_to`, `end_date_from`, `end_date_to`), location (`latitude`, `longitude`, `radius_km`), `category`, `neighborhood`, `search`, `relative_date`, and `use_cache`.
- Tool: `clear_cache` — clears the in-memory TTL cache.
- Resource: `ui://widget/sf-events.html` — serves the compiled widget markup; automatically embedded in tool results when available.

For exact behavior and returned structure, see:
- Server: `src/instacart_chatgpt/services/fastmcp_rec_events.py`
- Models: `src/instacart_chatgpt/services/events/models.py`
- Filters: `src/instacart_chatgpt/services/events/filtering.py`

## Dev workflow
- Run tests: `python -m pytest`
- Lint/format: `ruff check src tests` and `ruff format src tests`

## Project structure
- `src/instacart_chatgpt/services/fastmcp_rec_events.py` — MCP server (ASGI app) and tools
- `src/instacart_chatgpt/services/events/` — data models, filtering, and config
- `web/` — React/TypeScript widget (bundled with esbuild to `web/dist`)
- `requirements.txt` — Python deps (FastMCP, Uvicorn, httpx, etc.)
- `env` — dotenv-style config loaded by the server

---

Notes
- The server is configured in stateless streamable HTTP mode and exposes an ASGI app. The recommended client transport is Streamable HTTP.
- The widget must be built (step 2) before the tool can embed it; otherwise a minimal fallback HTML is returned.
