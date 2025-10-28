"""FastMCP server exposing SF Recreation & Parks event data."""

from __future__ import annotations

import html
import json
import logging
import os
import re
from collections.abc import Iterable
from functools import cache
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from cachetools import TTLCache
from dotenv import load_dotenv
from fastmcp import FastMCP  # type: ignore[attr-defined]
from fastmcp.server.context import Context
from fastmcp.tools.tool import ToolResult
from mcp.types import EmbeddedResource, TextContent, TextResourceContents
from pydantic import Field

from src.instacart_chatgpt.services.events import config
from src.instacart_chatgpt.services.events.filtering import EventFilter
from src.instacart_chatgpt.services.events.models import (
    Coordinates,
    EventCard,
    EventDates,
    EventLocation,
    MapData,
    MapMarker,
    SearchResponse,
    SearchSummary,
)

load_dotenv(dotenv_path="env")

logger = logging.getLogger("fastmcp.sfevents")
logging.basicConfig(level="INFO")

mcp = FastMCP(
    name="sf-rec-events",
    instructions=(
        "Browse upcoming San Francisco Recreation & Parks department programs "
        "from the public data.sfgov.org dataset."
    ),
    stateless_http=True,
)

# Initialize TTL cache: max 100 items, 5-minute (300 seconds) TTL
api_cache = TTLCache(maxsize=100, ttl=300)

DEFAULT_CITY_CENTER = Coordinates(**config.DEFAULT_CITY_CENTER)

TOOL_META: dict[str, Any] = {
    "openai/outputTemplate": config.WIDGET_URI,
    "openai/widgetAccessible": True,
    "openai/resultCanProduceWidget": True,
}
TOOL_ANNOTATIONS: dict[str, Any] = {
    "title": config.WIDGET_TITLE,
    "readOnlyHint": True,
    "openWorldHint": False,
}


class WidgetNotBuiltError(RuntimeError):
    """Raised when the widget bundle has not been built yet."""


def _clamp_limit(raw_limit: Any) -> int:
    """Coerce a raw limit value into a safe integer range."""

    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        value = config.DEFAULT_LIMIT

    return max(1, min(value, config.MAX_LIMIT))


def _make_cache_key(**kwargs: Any) -> str:
    """Stable cache key that ignores None values and orders keys."""

    serializable = {k: v for k, v in kwargs.items() if v is not None}
    return json.dumps(serializable, sort_keys=True, default=str)


async def _ctx_log(
        ctx: Context | None,
        level: Literal["debug", "info", "warning", "error"],
        message: str,
) -> None:
    """Log to both FastMCP context and standard logger when available."""

    getattr(logger, level)(message)

    if ctx is None:
        return

    ctx_method_name = level if level != "warning" else "warning"
    ctx_method = getattr(ctx, ctx_method_name, None)
    if ctx_method is not None:
        await ctx_method(message)


def _decode_text(text: str | None) -> str:
    return html.unescape(text or "")


def _normalize_url(url: str | None) -> str | None:
    if not url:
        return None
    url = url.strip()
    if not url:
        return None
    if not url.startswith(("http://", "https://")):
        return f"https://{url}"
    return url


def _build_event_card(event: dict[str, Any]) -> EventCard:
    link = (
            event.get("registration_url")
            or event.get("registration_link")
            or event.get("more_info")
            or event.get("event_website")
    )
    normalized_link = _normalize_url(link)

    coordinates = None
    try:
        if event.get("latitude") and event.get("longitude"):
            coordinates = Coordinates(
                lat=float(event["latitude"]),
                lng=float(event["longitude"]),
            )
    except (TypeError, ValueError):
        coordinates = None

    distance = event.get("distance_km")
    if isinstance(distance, str):
        try:
            distance = float(distance)
        except ValueError:
            distance = None

    description = _decode_text(event.get("event_details")) or None

    return EventCard(
        title=_decode_text(event.get("event_name", "Untitled Event")),
        dates=EventDates(
            start=event.get("event_start_date"),
            end=event.get("event_end_date"),
        ),
        category=_decode_text(event.get("events_category")) or None,
        location=EventLocation(
            name=_decode_text(
                event.get("location_name")
                or event.get("site_location_name")
                or "",
            ),
            neighborhood=_decode_text(event.get("analysis_neighborhood")) or None,
            address=_decode_text(
                event.get("address")
                or event.get("site_address")
                or "",
            )
                    or None,
        ),
        distance_km=distance,
        coordinates=coordinates,
        description=description,
        details_url=normalized_link,
        registration_url=_decode_text(event.get("registration_url")) or None,
        more_info=normalized_link if event.get("more_info") else None,
    )


def _build_map_data(event_cards: list[EventCard]) -> MapData:
    markers = [marker for event in event_cards if (marker := MapMarker.from_event(event))]
    coordinates = [marker.coordinates for marker in markers]
    center = Coordinates.average(coordinates) or DEFAULT_CITY_CENTER

    return MapData(
        markers=markers,
        center=center,
        default_center=DEFAULT_CITY_CENTER,
        marker_count=len(markers),
    )


def _extract_relative_date_from_search(
        search: str | None,
        relative_date: str | None,
) -> tuple[str | None, str | None]:
    """Strip relative-date keywords from search text and return derived keyword."""

    if not search:
        return None, relative_date

    normalized = search
    derived_keyword = relative_date
    lowered = search.lower()

    for keyword in sorted(config.RELATIVE_DATE_KEYWORDS, key=len, reverse=True):
        if keyword in lowered:
            derived_keyword = derived_keyword or config.RELATIVE_DATE_KEYWORDS[keyword]
            pattern = re.compile(rf"\b{re.escape(keyword)}\b", flags=re.IGNORECASE)
            normalized = pattern.sub(" ", normalized)
            lowered = normalized.lower()

    normalized = " ".join(normalized.split())
    return normalized or None, derived_keyword


async def _fetch_events(
        fetch_limit: int,
        use_cache: bool,
        ctx: Context | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """Fetch raw events from Socrata with caching and optional logging."""

    cache_key = _make_cache_key(limit=fetch_limit)
    payload: list[dict[str, Any]] | None = None
    from_cache = False

    if use_cache and cache_key in api_cache:
        payload = api_cache[cache_key]
        from_cache = True
        await _ctx_log(ctx, "debug", f"Cache hit for key {cache_key}")

    if payload is None:
        params: dict[str, Any] = {
            "$limit": fetch_limit,
            "$order": "event_start_date ASC",
        }
        await _ctx_log(
            ctx,
            "info",
            f"Fetching SF Rec & Park events from API (limit={params['$limit']})",
        )

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    config.API_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        "X-App-Token": os.getenv("APPTOKEN", "STkpW9v5bxHaghK4Y5nmp3BzC"),
                    },
                )
                response.raise_for_status()
            payload = response.json()
            if payload:
                api_cache[cache_key] = payload
                await _ctx_log(ctx, "debug", f"Cache set for key {cache_key}")
        except httpx.HTTPError as exc:
            message = f"Failed to fetch events from API: {exc}"
            await _ctx_log(ctx, "error", message)
            raise RuntimeError(message) from exc
        except Exception as exc:  # pragma: no cover - defensive logging
            message = f"Unexpected error fetching events: {exc}"
            await _ctx_log(ctx, "error", message)
            raise RuntimeError(message) from exc

    payload = payload or []
    await _ctx_log(
        ctx,
        "debug",
        f"Fetched {len(payload)} raw events (from_cache={from_cache})",
    )
    return payload, from_cache


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


@cache
def _load_widget_html() -> str:
    """Load the widget HTML from the built component."""
    dist_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    component_path = dist_dir / "component.js"
    css_path = dist_dir / "component.css"

    if not component_path.exists():
        raise WidgetNotBuiltError(
            "Widget bundle missing. Run `npm run build` in the web directory to generate "
            f"{component_path.name}."
        )

    component_code = component_path.read_text(encoding="utf8")
    component_css = css_path.read_text(encoding="utf8") if css_path.exists() else ""

    return f'''
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
                body {{
                    margin: 0;
                    padding: 0;
                    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
                }}
                {component_css}
            </style>
        </head>
        <body>
            <div id="root"></div>
            <script type="module">
                {component_code}
            </script>
        </body>
        </html>
    '''


def _fallback_widget_html() -> str:
    """Return a minimal placeholder widget when assets are missing."""
    return (
        '<!DOCTYPE html>'
        '<html><head><meta charset="UTF-8" />'
        '<style>body { font-family: sans-serif; padding: 1rem; }</style>'
        '</head><body>'
        '<h2>SF Events Widget</h2>'
        '<p>The interactive widget is unavailable because the build output is missing.</p>'
        '</body></html>'
    )


def _tool_meta() -> dict[str, Any]:
    """Return metadata for the tool/resource."""
    return TOOL_META.copy()


def _result_meta(widget: EmbeddedResource) -> dict[str, Any]:
    """Metadata describing the widget result for OpenAI-compatible clients."""
    widget_payload = widget.model_dump(mode="json", exclude_none=True)
    return {
        **TOOL_META,
        "openai/toolInvocation/invoking": "Searching SF events",
        "openai/toolInvocation/invoked": "Found SF events",
        "openai.com/widget": widget_payload,
    }


def _embedded_widget_resource() -> EmbeddedResource:
    """Create an embedded widget resource."""
    annotations: dict[str, Any] | None = None
    try:
        html_markup = _load_widget_html()
    except WidgetNotBuiltError as exc:
        logger.warning("Widget markup missing; using fallback widget. %s", exc)
        html_markup = _fallback_widget_html()
        annotations = {"fastmcp/widgetFallback": True}

    return EmbeddedResource(
        type="resource",
        resource=TextResourceContents(
            uri=config.WIDGET_URI,
            mimeType=config.MIME_TYPE,
            text=html_markup,
            title=config.WIDGET_TITLE,
        ),
        annotations=annotations,
    )


@mcp.tool(
    name="search_sf_events",
    description="Search and display San Francisco Recreation & Parks events",
    annotations=TOOL_ANNOTATIONS,
    meta=TOOL_META,
)
async def search_sf_events(
        limit: Annotated[
            int,
            Field(
                description="Maximum number of events to return",
                ge=1,
                le=config.MAX_LIMIT,
            ),
        ] = config.DEFAULT_LIMIT,
        start_date_from: Annotated[
            str | None,
            Field(description="Filter events starting on or after this date (YYYY-MM-DD)"),
        ] = None,
        start_date_to: Annotated[
            str | None,
            Field(description="Filter events starting on or before this date (YYYY-MM-DD)"),
        ] = None,
        end_date_from: Annotated[
            str | None,
            Field(description="Filter events ending on or after this date (YYYY-MM-DD)"),
        ] = None,
        end_date_to: Annotated[
            str | None,
            Field(description="Filter events ending on or before this date (YYYY-MM-DD)"),
        ] = None,
        latitude: Annotated[
            float | None,
            Field(description="Center latitude for proximity search", ge=-90.0, le=90.0),
        ] = None,
        longitude: Annotated[
            float | None,
            Field(description="Center longitude for proximity search", ge=-180.0, le=180.0),
        ] = None,
        radius_km: Annotated[
            float,
            Field(description="Search radius in kilometers", gt=0.0, le=100.0),
        ] = 5.0,
        category: Annotated[
            str | None,
            Field(description="Filter by category (e.g., Sports, Arts)"),
        ] = None,
        neighborhood: Annotated[
            str | None,
            Field(description="Filter by neighborhood"),
        ] = None,
        search: Annotated[
            str | None,
            Field(description="Free-text search across event title, details, and location"),
        ] = None,
        relative_date: Annotated[
            str | None,
            Field(description="Relative date keyword (e.g., today, tomorrow, weekend)"),
        ] = None,
        use_cache: Annotated[
            bool,
            Field(description="Use cached API payloads when available"),
        ] = True,
        ctx: Context | None = None,
) -> ToolResult:
    """Primary search entrypoint for the SF Recreation & Parks dataset."""

    # Normalize inputs
    limit = _clamp_limit(limit)
    radius_km = radius_km if radius_km > 0 else 5.0
    normalized_search, derived_keyword = _extract_relative_date_from_search(
        search, relative_date
    )
    relative_keyword = derived_keyword

    filters_debug = {
        "limit": limit,
        "start_date_from": start_date_from,
        "start_date_to": start_date_to,
        "end_date_from": end_date_from,
        "end_date_to": end_date_to,
        "latitude": latitude,
        "longitude": longitude,
        "radius_km": radius_km,
        "category": category,
        "neighborhood": neighborhood,
        "search": normalized_search,
        "relative_date": relative_keyword,
        "use_cache": use_cache,
    }
    logger.info("search_sf_events arguments: %s", filters_debug)
    await _ctx_log(ctx, "debug", f"search_sf_events filters: {json.dumps(filters_debug)}")

    fetch_limit = min(
        config.MAX_FETCH_LIMIT,
        max(limit * config.FETCH_LIMIT_MULTIPLIER, limit),
    )

    payload, from_cache = await _fetch_events(fetch_limit, use_cache, ctx)

    filtered_payload = EventFilter.apply_all_filters(
        payload,
        start_date_from=start_date_from,
        start_date_to=start_date_to,
        end_date_from=end_date_from,
        end_date_to=end_date_to,
        latitude=latitude,
        longitude=longitude,
        radius_km=radius_km,
        category=category,
        neighborhood=neighborhood,
        search=normalized_search,
        relative_date=relative_keyword,
    )

    event_cards = [_build_event_card(event) for event in filtered_payload[:limit]]
    map_data = _build_map_data(event_cards)

    summary = SearchSummary(
        total_found=len(filtered_payload),
        showing=len(event_cards),
        from_cache=from_cache,
    )
    structured_response = SearchResponse(
        summary=summary,
        events=event_cards,
        map=map_data,
    )

    summary_message = (
        "Returning "
        f"{summary.showing} of "
        f"{summary.total_found} filtered events"
    )

    await _ctx_log(ctx, "info", summary_message)

    widget_resource = _embedded_widget_resource()
    if (
            getattr(widget_resource, "annotations", None)
            and widget_resource.annotations.get("fastmcp/widgetFallback")
    ):
        await _ctx_log(ctx, "warning", "Widget assets missing; using fallback markup.")
    message = f"Found {summary.showing} SF Recreation & Parks events!"

    content_blocks = [
        TextContent(
            type="text",
            text=message,
            meta=_result_meta(widget_resource),
        ),
        widget_resource,
    ]

    return ToolResult(
        content=content_blocks,
        structured_content=structured_response.model_dump(),
    )


@mcp.resource(
    config.WIDGET_URI,
    name=config.WIDGET_TITLE,
    description="SF Recreation & Parks Events widget markup",
    mime_type=config.MIME_TYPE,
    annotations={"readOnlyHint": True, "idempotentHint": True},
    meta=_tool_meta(),
)
def widget_markup() -> str:
    """Expose the pre-built widget markup as a read-only resource."""

    return _load_widget_html()


@mcp.tool("clear_cache")
async def clear_cache() -> dict[str, str]:
    """Clear the API cache manually."""
    api_cache.clear()
    logger.info("Cache cleared")
    return {'status': 'success', 'message': 'Cache cleared successfully'}


# Create ASGI app with CORS
app = mcp.streamable_http_app()

try:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
except Exception:
    pass

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("fastmcp_rec_events:app", host="0.0.0.0", port=8000, reload=True)
