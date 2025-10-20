"""Single-file FastMCP server exposing SF Rec & Park event data."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from typing import Any

import httpx

from fastmcp import FastMCP  # type: ignore[attr-defined]


logger = logging.getLogger("fastmcp.sfevents")
logging.basicConfig(level="INFO")

API_URL = "https://data.sfgov.org/api/v3/views/8i3s-ih2a/query.json"

mcp = FastMCP(
    name="sf-rec-events",
    description=(
        "Browse upcoming San Francisco Recreation & Parks department programs "
        "from the public data.sfgov.org dataset."
    ),
)


def _extract_column_names(columns: Iterable[Any]) -> list[str]:
    """Return column names from Socrata metadata with defensive parsing."""
    names: list[str] = []
    for column in columns:
        if isinstance(column, dict):
            name = column.get("name") or column.get("fieldName") or column.get("id")
        elif isinstance(column, list) and column:
            name = str(column[0])
        else:
            name = None
        if name:
            names.append(str(name))
    return names


@mcp.tool(
    name="fetch_rec_events",
    description=(
        "Return a slice of SF Rec & Park events with metadata sourced from data.sfgov.org."
    ),
)
async def fetch_rec_events(limit: int = 5) -> dict[str, Any]:
    """Retrieve upcoming Recreation & Parks events."""
    bounded_limit = max(1, min(limit, 100))
    params = {"limit": bounded_limit}
    logger.info("Fetching SF Rec & Park events", extra={"params": params})

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(API_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    data = payload.get("data", [])
    meta = payload.get("meta", {})
    column_defs = meta.get("view", {}).get("columns", []) if isinstance(meta, dict) else []
    column_names = _extract_column_names(column_defs)

    records: list[dict[str, Any]] = []
    for row in data:
        if isinstance(row, list) and column_names:
            record = {column_names[idx]: value for idx, value in enumerate(row)}
        elif isinstance(row, dict):
            record = {str(key): value for key, value in row.items()}
        else:
            record = {"raw": row}
        records.append(record)

    return {
        "source": API_URL,
        "count": len(records),
        "limit": bounded_limit,
        "records": records,
    }


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    mcp.run()
