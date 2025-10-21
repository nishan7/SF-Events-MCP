"""Single-file FastMCP server exposing SF Rec & Park event data."""

from __future__ import annotations

import html
import logging
import os
from collections.abc import Iterable
from typing import Any
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2
from pathlib import Path
from functools import lru_cache

import httpx
from dotenv import load_dotenv
from cachetools import TTLCache
import mcp.types as types

load_dotenv(dotenv_path='env')

from fastmcp import FastMCP  # type: ignore[attr-defined]
from mcp.server.fastmcp import Context
from fastmcp.server.dependencies import get_context

logger = logging.getLogger("fastmcp.sfevents")
logging.basicConfig(level="INFO")

API_URL = "https://data.sfgov.org/api/v3/views/8i3s-ih2a/query.json"

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

MIME_TYPE = "text/html+skybridge"
WIDGET_URI = "ui://widget/sf-events.html"
WIDGET_TITLE = "SF Recreation & Parks Events"


class EventFilter:
    """Filter events by various criteria."""

    @staticmethod
    def parse_date_string(date_str: str) -> date | None:
        """Parse a date string in various formats to a date object."""
        if not date_str:
            return None

        try:
            # Try ISO format with time: "2025-11-13T00:00:00.000"
            if 'T' in date_str:
                return datetime.fromisoformat(date_str.split('.')[0]).date()
            # Try simple date format: "2025-11-13"
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            logger.warning(f"Failed to parse date: {date_str}")
            return None

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the distance between two coordinates using Haversine formula.

        Args:
            lat1, lon1: First coordinate (latitude, longitude)
            lat2, lon2: Second coordinate (latitude, longitude)

        Returns:
            Distance in kilometers
        """
        # Earth's radius in kilometers
        R = 6371.0

        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = R * c
        return distance

    @classmethod
    def filter_by_date(
            cls,
            events: list[dict[str, Any]],
            start_date_from: str | None = None,
            start_date_to: str | None = None,
            end_date_from: str | None = None,
            end_date_to: str | None = None
    ) -> list[dict[str, Any]]:
        """Filter events by date ranges after fetching from API.

        Args:
            events: List of event dictionaries to filter
            start_date_from: Filter events starting from this date (YYYY-MM-DD format)
            start_date_to: Filter events starting before this date (YYYY-MM-DD format)
            end_date_from: Filter events ending from this date (YYYY-MM-DD format)
            end_date_to: Filter events ending before this date (YYYY-MM-DD format)

        Returns:
            Filtered list of events
        """
        if not any([start_date_from, start_date_to, end_date_from, end_date_to]):
            return events

        # Parse filter dates
        filter_start_from = cls.parse_date_string(start_date_from) if start_date_from else None
        filter_start_to = cls.parse_date_string(start_date_to) if start_date_to else None
        filter_end_from = cls.parse_date_string(end_date_from) if end_date_from else None
        filter_end_to = cls.parse_date_string(end_date_to) if end_date_to else None

        filtered_events = []

        for event in events:
            event_start = cls.parse_date_string(event.get("event_start_date", ""))
            event_end = cls.parse_date_string(event.get("event_end_date", ""))

            # Apply filters
            if filter_start_from and event_start and event_start < filter_start_from:
                continue

            if filter_start_to and event_start and event_start > filter_start_to:
                continue

            if filter_end_from and event_end and event_end < filter_end_from:
                continue

            if filter_end_to and event_end and event_end > filter_end_to:
                continue

            filtered_events.append(event)

        return filtered_events

    @classmethod
    def filter_by_location(
            cls,
            events: list[dict[str, Any]],
            latitude: float | None = None,
            longitude: float | None = None,
            radius_km: float = 5.0
    ) -> list[dict[str, Any]]:
        """Filter events by proximity to coordinates.

        Args:
            events: List of event dictionaries to filter
            latitude: Center latitude for proximity search
            longitude: Center longitude for proximity search
            radius_km: Maximum distance in kilometers (default: 5.0)

        Returns:
            Filtered list of events within the radius
        """
        if latitude is None or longitude is None:
            return events

        filtered_events = []

        for event in events:
            try:
                event_lat = float(event.get("latitude", 0))
                event_lon = float(event.get("longitude", 0))

                if event_lat and event_lon:
                    distance = cls.calculate_distance(latitude, longitude, event_lat, event_lon)
                    if distance <= radius_km:
                        # Add distance to event for reference
                        event_copy = event.copy()
                        event_copy["distance_km"] = round(distance, 2)
                        filtered_events.append(event_copy)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse coordinates for event: {e}")
                continue

        # Sort by distance
        filtered_events.sort(key=lambda x: x.get("distance_km", float('inf')))

        return filtered_events

    @staticmethod
    def filter_by_category(
            events: list[dict[str, Any]],
            category: str | None = None
    ) -> list[dict[str, Any]]:
        """Filter events by category.

        Args:
            events: List of event dictionaries to filter
            category: Category name to filter by (case-insensitive partial match)

        Returns:
            Filtered list of events matching the category
        """
        if not category:
            return events

        category_lower = category.lower()
        filtered_events = []

        for event in events:
            event_category = event.get("events_category", "")
            if event_category and category_lower in event_category.lower():
                filtered_events.append(event)

        return filtered_events

    @staticmethod
    def filter_by_neighborhood(
            events: list[dict[str, Any]],
            neighborhood: str | None = None
    ) -> list[dict[str, Any]]:
        """Filter events by neighborhood.

        Args:
            events: List of event dictionaries to filter
            neighborhood: Neighborhood name to filter by (case-insensitive partial match)

        Returns:
            Filtered list of events matching the neighborhood
        """
        if not neighborhood:
            return events

        neighborhood_lower = neighborhood.lower()
        filtered_events = []

        for event in events:
            event_neighborhood = event.get("analysis_neighborhood", "")
            if event_neighborhood and neighborhood_lower in event_neighborhood.lower():
                filtered_events.append(event)

        return filtered_events

    @classmethod
    def apply_all_filters(
            cls,
            events: list[dict[str, Any]],
            start_date_from: str | None = None,
            start_date_to: str | None = None,
            end_date_from: str | None = None,
            end_date_to: str | None = None,
            latitude: float | None = None,
            longitude: float | None = None,
            radius_km: float = 5.0,
            category: str | None = None,
            neighborhood: str | None = None
    ) -> list[dict[str, Any]]:
        """Apply all filters to the events list.

        Args:
            events: List of event dictionaries to filter
            start_date_from: Filter events starting from this date (YYYY-MM-DD format)
            start_date_to: Filter events starting before this date (YYYY-MM-DD format)
            end_date_from: Filter events ending from this date (YYYY-MM-DD format)
            end_date_to: Filter events ending before this date (YYYY-MM-DD format)
            latitude: Center latitude for proximity search
            longitude: Center longitude for proximity search
            radius_km: Maximum distance in kilometers (default: 5.0)
            category: Filter by event category (case-insensitive partial match)
            neighborhood: Filter by neighborhood (case-insensitive partial match)

        Returns:
            Filtered list of events
        """
        filtered = events

        # Apply date filters
        filtered = cls.filter_by_date(
            filtered,
            start_date_from=start_date_from,
            start_date_to=start_date_to,
            end_date_from=end_date_from,
            end_date_to=end_date_to
        )

        # Apply location filters
        filtered = cls.filter_by_location(
            filtered,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km
        )

        # Apply category filters
        filtered = cls.filter_by_category(filtered, category=category)

        # Apply neighborhood filters
        filtered = cls.filter_by_neighborhood(filtered, neighborhood=neighborhood)

        return filtered


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


def format_event_card(event: dict[str, Any]) -> dict[str, Any]:
    """Format a single event into a clean card structure.

    Args:
        event: Raw event data from API

    Returns:
        Simplified event card with only relevant fields
    """
    # Decode HTML entities in text fields
    def decode_text(text: str | None) -> str:
        if not text:
            return ""
        return html.unescape(text)

    card = {
        "title": decode_text(event.get("event_name", "Untitled Event")),
        "dates": {
            "start": event.get("event_start_date", ""),
            "end": event.get("event_end_date", "")
        },
        "category": decode_text(event.get("events_category", "")),
        "location": {
            "name": decode_text(event.get("location_name", "")),
            "neighborhood": decode_text(event.get("analysis_neighborhood", "")),
            "address": decode_text(event.get("address", ""))
        }
    }

    # Add optional fields only if they exist
    if event.get("distance_km"):
        card["distance_km"] = event["distance_km"]

    if event.get("latitude") and event.get("longitude"):
        card["coordinates"] = {
            "lat": float(event["latitude"]),
            "lng": float(event["longitude"])
        }

    if event.get("event_details"):
        card["description"] = decode_text(event["event_details"])

    if event.get("registration_url"):
        card["registration_url"] = decode_text(event["registration_url"])

    return card


@lru_cache(maxsize=None)
def _load_widget_html() -> str:
    """Load the widget HTML from the built component."""
    component_path = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist" / "component.js"
    if not component_path.exists():
        raise FileNotFoundError(
            f'Widget component not found at {component_path}. '
            "Run `npm run build` in the web directory to generate the component."
        )

    component_code = component_path.read_text(encoding="utf8")

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


def _tool_meta() -> dict[str, Any]:
    """Return metadata for the tool/resource."""
    return {
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Searching SF events",
        "openai/toolInvocation/invoked": "Found SF events",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True
    }


def _embedded_widget_resource() -> types.EmbeddedResource:
    """Create an embedded widget resource."""
    return types.EmbeddedResource(
        type="resource",
        resource=types.TextResourceContents(
            uri=WIDGET_URI,
            mimeType=MIME_TYPE,
            text=_load_widget_html(),
            title=WIDGET_TITLE,
        ),
    )


# Override list_tools to add proper metadata
@mcp._mcp_server.list_tools()
async def _list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="search_sf_events",
            title=WIDGET_TITLE,
            description="Search and display San Francisco Recreation & Parks events with filters",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Maximum number of events (1-100)", "default": 5},
                    "start_date_from": {"type": "string", "description": "Filter events starting from date (YYYY-MM-DD)"},
                    "start_date_to": {"type": "string", "description": "Filter events starting before date (YYYY-MM-DD)"},
                    "category": {"type": "string", "description": "Filter by category (e.g., Sports, Arts)"},
                    "neighborhood": {"type": "string", "description": "Filter by neighborhood"},
                    "latitude": {"type": "number", "description": "Center latitude for proximity search"},
                    "longitude": {"type": "number", "description": "Center longitude for proximity search"},
                    "radius_km": {"type": "number", "description": "Search radius in km", "default": 5.0}
                },
                "additionalProperties": False,
            },
            _meta=_tool_meta(),
            annotations={
                "destructiveHint": False,
                "openWorldHint": False,
                "readOnlyHint": True,
            },
        )
    ]


# Override list_resources
@mcp._mcp_server.list_resources()
async def _list_resources() -> list[types.Resource]:
    return [
        types.Resource(
            name=WIDGET_TITLE,
            title=WIDGET_TITLE,
            uri=WIDGET_URI,
            description="SF Recreation & Parks Events widget markup",
            mimeType=MIME_TYPE,
            _meta=_tool_meta(),
        )
    ]


# Override list_resource_templates
@mcp._mcp_server.list_resource_templates()
async def _list_resource_templates() -> list[types.ResourceTemplate]:
    return [
        types.ResourceTemplate(
            name=WIDGET_TITLE,
            title=WIDGET_TITLE,
            uriTemplate=WIDGET_URI,
            description="SF Recreation & Parks Events widget markup",
            mimeType=MIME_TYPE,
            _meta=_tool_meta(),
        )
    ]


# Override read_resource handler
async def _handle_read_resource(req: types.ReadResourceRequest) -> types.ServerResult:
    if str(req.params.uri) != WIDGET_URI:
        return types.ServerResult(
            types.ReadResourceResult(
                contents=[],
                _meta={"error": f"Unknown resource: {req.params.uri}"},
            )
        )

    contents = [
        types.TextResourceContents(
            uri=WIDGET_URI,
            mimeType=MIME_TYPE,
            text=_load_widget_html(),
            _meta=_tool_meta(),
        )
    ]

    return types.ServerResult(types.ReadResourceResult(contents=contents))


# Override call_tool handler
async def _call_tool_request(req: types.CallToolRequest) -> types.ServerResult:
    if req.params.name != "search_sf_events":
        return types.ServerResult(
            types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=f"Unknown tool: {req.params.name}",
                    )
                ],
                isError=True,
            )
        )

    # Extract arguments
    arguments = req.params.arguments or {}
    limit = arguments.get("limit", 5)
    start_date_from = arguments.get("start_date_from")
    start_date_to = arguments.get("start_date_to")
    end_date_from = arguments.get("end_date_from")
    end_date_to = arguments.get("end_date_to")
    latitude = arguments.get("latitude")
    longitude = arguments.get("longitude")
    radius_km = arguments.get("radius_km", 5.0)
    category = arguments.get("category")
    neighborhood = arguments.get("neighborhood")
    use_cache = arguments.get("use_cache", True)

    logger.info('Request', arguments)

    # Create cache key
    cache_key = f"events_limit_{limit}"

    # Try to get from cache
    payload = None
    from_cache = False
    if use_cache and cache_key in api_cache:
        payload = api_cache[cache_key]
        from_cache = True
        logger.info(f"Cache hit for key: {cache_key}")

    # Fetch from API if not in cache
    if payload is None:
        params: dict[str, Any] = {}
        logger.info("Fetching SF Rec & Park events from API")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    API_URL,
                    params=params,
                    headers={
                        "Accept": "application/json",
                        'X-App-Token': os.getenv('APPTOKEN', 'STkpW9v5bxHaghK4Y5nmp3BzC')
                    }
                )
                response.raise_for_status()
                payload = response.json()

            # Store in cache
            if payload and len(payload) > 0:
                api_cache[cache_key] = payload
                logger.info(f"Cache set for key: {cache_key}")
        except Exception as e:
            logger.error(f"API error: {e}")
            return types.ServerResult(
                types.CallToolResult(
                    content=[
                        types.TextContent(
                            type="text",
                            text=f"Failed to fetch events: {str(e)}",
                        )
                    ],
                    isError=True,
                )
            )

    # Process and filter events
    if payload and len(payload) > 0:
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
            neighborhood=neighborhood
        )

        event_cards = [format_event_card(event) for event in filtered_payload[:limit]]

        structured_content = {
            'summary': {
                'total_found': len(filtered_payload),
                'showing': len(event_cards),
                'from_cache': from_cache
            },
            'events': event_cards
        }
    else:
        structured_content = {
            'summary': {
                'total_found': 0,
                'showing': 0,
                'from_cache': from_cache
            },
            'events': []
        }

    logger.info('Response', structured_content)

    # Create widget resource
    widget_resource = _embedded_widget_resource()

    # Metadata for widget
    meta: dict[str, Any] = {
        "openai.com/widget": widget_resource.model_dump(mode="json"),
        "openai/outputTemplate": WIDGET_URI,
        "openai/toolInvocation/invoking": "Searching SF events",
        "openai/toolInvocation/invoked": "Found SF events",
        "openai/widgetAccessible": True,
        "openai/resultCanProduceWidget": True,
    }

    return types.ServerResult(
        types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=f"Found {structured_content['summary']['showing']} SF Recreation & Parks events!",
                )
            ],
            structuredContent=structured_content,
            _meta=meta
        )
    )


# Register custom handlers
mcp._mcp_server.request_handlers[types.CallToolRequest] = _call_tool_request
mcp._mcp_server.request_handlers[types.ReadResourceRequest] = _handle_read_resource


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
