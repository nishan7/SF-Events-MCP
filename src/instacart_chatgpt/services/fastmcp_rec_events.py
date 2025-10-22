"""Single-file FastMCP server exposing SF Rec & Park event data."""

from __future__ import annotations

import html
import json
import logging
import os
import re
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from functools import cache
from math import atan2, cos, radians, sin, sqrt
from pathlib import Path
from typing import Any

import httpx
import mcp.types as types
from cachetools import TTLCache
from dotenv import load_dotenv
from fastmcp import FastMCP  # type: ignore[attr-defined]

load_dotenv(dotenv_path="env")

logger = logging.getLogger("fastmcp.sfevents")
logging.basicConfig(level="INFO")

API_URL = "https://data.sfgov.org/api/v3/views/8i3s-ih2a/query.json"

DEFAULT_LIMIT = 3
MAX_LIMIT = 25
FETCH_LIMIT_MULTIPLIER = 4
MAX_FETCH_LIMIT = 100

RELATIVE_DATE_KEYWORDS: dict[str, str] = {
    "today": "today",
    "tonight": "today",
    "tomorrow": "tomorrow",
    "tmrw": "tomorrow",
    "weekend": "weekend",
    "this weekend": "weekend",
}

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
WIDGET_TITLE = "SF Events"
DEFAULT_CITY_CENTER = {"lat": 37.7749, "lng": -122.4194}


def _clamp_limit(raw_limit: Any) -> int:
    """Coerce a raw limit value into a safe integer range."""
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        value = DEFAULT_LIMIT

    return max(1, min(value, MAX_LIMIT))


def _make_cache_key(**kwargs: Any) -> str:
    """Stable cache key that ignores None values and orders keys."""

    serializable = {k: v for k, v in kwargs.items() if v is not None}
    return json.dumps(serializable, sort_keys=True, default=str)


def _average_coordinates(events: list[dict[str, Any]]) -> dict[str, float] | None:
    """Return average lat/lng from events with coordinates, or None."""

    total_lat = 0.0
    total_lng = 0.0
    count = 0

    for event in events:
        coords = event.get("coordinates")
        if not coords:
            continue
        total_lat += coords["lat"]
        total_lng += coords["lng"]
        count += 1

    if count == 0:
        return None

    return {"lat": total_lat / count, "lng": total_lng / count}


def _build_map_markers(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build lightweight marker representations for map views."""

    markers: list[dict[str, Any]] = []
    for event in events:
        coords = event.get("coordinates")
        if not coords:
            continue
        markers.append(
            {
                "title": event.get("title", ""),
                "category": event.get("category", ""),
                "coordinates": coords,
                "location": event.get("location", {}),
                "details_url": event.get("details_url") or event.get("registration_url"),
            }
        )

    return markers


def _to_float(value: Any) -> float | None:
    """Best-effort float conversion that returns None on failure."""

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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
        earth_radius_km = 6371.0

        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        distance = earth_radius_km * c
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
            neighborhood: str | None = None,
            search: str | None = None,
            relative_date: str | None = None,
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
            search: Free-text search across event metadata
            relative_date: Relative date descriptor (e.g., "today", "tomorrow")

        Returns:
            Filtered list of events
        """
        filtered = cls.filter_upcoming(events)

        if relative_date:
            start_from, start_to = cls.relative_date_window(relative_date)
            if start_from and start_to:
                start_date_from = start_from if start_date_from is None else start_date_from
                start_date_to = start_to if start_date_to is None else start_date_to

        # Apply date filters
        filtered = cls.filter_by_date(
            filtered,
            start_date_from=start_date_from,
            start_date_to=start_date_to,
            end_date_from=end_date_from,
            end_date_to=end_date_to
        )

        # Apply category filters
        filtered = cls.filter_by_category(filtered, category=category)

        # Apply neighborhood filters
        filtered = cls.filter_by_neighborhood(filtered, neighborhood=neighborhood)

        # Apply search filter
        filtered = cls.filter_by_search(filtered, search=search)

        # Apply location filters last to compute distance metadata
        filtered = cls.filter_by_location(
            filtered,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km
        )

        return filtered

    @staticmethod
    def filter_upcoming(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only events that have not yet concluded."""

        today = date.today()
        upcoming: list[dict[str, Any]] = []

        for event in events:
            start_date = EventFilter.parse_date_string(event.get("event_start_date", ""))
            end_date = EventFilter.parse_date_string(event.get("event_end_date", ""))

            if start_date and start_date >= today:
                upcoming.append(event)
                continue

            if end_date and end_date >= today:
                upcoming.append(event)
                continue

            if not start_date and not end_date:
                upcoming.append(event)

        return upcoming

    @staticmethod
    def relative_date_window(keyword: str) -> tuple[str | None, str | None]:
        """Return an inclusive date range string pair for a keyword."""
        keyword_normalized = keyword.strip().lower()
        if not keyword_normalized:
            return None, None

        today = date.today()
        if keyword_normalized in {"today", "tonight"}:
            target = today
            return target.isoformat(), target.isoformat()
        if keyword_normalized in {"tomorrow", "tmrw"}:
            target = today + timedelta(days=1)
            return target.isoformat(), target.isoformat()
        if keyword_normalized in {"weekend", "this weekend"}:
            saturday_offset = (5 - today.weekday()) % 7
            saturday = today + timedelta(days=saturday_offset)
            sunday = saturday + timedelta(days=1)
            return saturday.isoformat(), sunday.isoformat()

        return None, None

    @staticmethod
    def filter_by_search(
            events: list[dict[str, Any]],
            search: str | None = None
    ) -> list[dict[str, Any]]:
        """Filter events by free-text search across common fields."""
        if not search:
            return events

        query = search.strip().lower()
        if not query:
            return events

        tokens = [token for token in re.split(r"\W+", query) if token]

        filtered_events: list[dict[str, Any]] = []
        for event in events:
            haystack_parts = [
                event.get("event_name"),
                event.get("event_details"),
                event.get("analysis_neighborhood"),
                event.get("events_category"),
                event.get("location_name"),
                event.get("address"),
            ]
            haystack = " ".join(str(part) for part in haystack_parts if part).lower()
            if not haystack:
                continue

            if query in haystack:
                filtered_events.append(event)
                continue

            if EventFilter._fuzzy_match(query, tokens, haystack):
                filtered_events.append(event)

        return filtered_events

    @staticmethod
    def _fuzzy_match(query: str, tokens: list[str], haystack: str) -> bool:
        """Return True if query roughly matches haystack."""
        from difflib import SequenceMatcher

        ratio = SequenceMatcher(None, query, haystack).ratio()
        if ratio >= 0.55:
            return True

        if not tokens:
            return False

        haystack_tokens = [token for token in re.split(r"\W+", haystack) if token]
        if not haystack_tokens:
            return False

        match_scores: list[float] = []
        for token in tokens:
            best = 0.0
            for candidate in haystack_tokens:
                score = SequenceMatcher(None, token, candidate).ratio()
                if score > best:
                    best = score
                if best >= 0.75:
                    break
            match_scores.append(best)

        if not match_scores:
            return False

        avg_score = sum(match_scores) / len(match_scores)
        return avg_score >= 0.62


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

    def normalize_url(url: str | None) -> str | None:
        if not url:
            return None
        url = url.strip()
        if not url:
            return None
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return url

    link = (
        event.get("registration_url")
        or event.get("registration_link")
        or event.get("more_info")
        or event.get("event_website")
    )
    normalized_link = normalize_url(link)

    card = {
        "title": decode_text(event.get("event_name", "Untitled Event")),
        "dates": {
            "start": event.get("event_start_date", ""),
            "end": event.get("event_end_date", "")
        },
        "category": decode_text(event.get("events_category", "")),
        "location": {
            "name": decode_text(
                event.get("location_name")
                or event.get("site_location_name")
                or ""
            ),
            "neighborhood": decode_text(event.get("analysis_neighborhood", "")),
            "address": decode_text(
                event.get("address")
                or event.get("site_address")
                or ""
            )
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

    if normalized_link:
        card["details_url"] = normalized_link

    if event.get("registration_url"):
        card["registration_url"] = decode_text(event["registration_url"])

    if event.get("more_info") and normalized_link:
        card["more_info"] = normalized_link

    return card


@cache
def _load_widget_html() -> str:
    """Load the widget HTML from the built component."""
    dist_dir = Path(__file__).resolve().parent.parent.parent.parent / "web" / "dist"
    component_path = dist_dir / "component.js"
    css_path = dist_dir / "component.css"

    if not component_path.exists():
        raise FileNotFoundError(
            f'Widget component not found at {component_path}. '
            "Run `npm run build` in the web directory to generate the component."
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
            description="Search and display San Francisco events with filters",
            inputSchema={
                "type": "object",

                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of events to return, defaults to 3",
                        "default": DEFAULT_LIMIT,
                    },
                    "start_date_from": {
                        "type": "string",
                        "description": (
                            "Filter events starting from date (YYYY-MM-DD)"
                        ),
                    },
                    "start_date_to": {
                        "type": "string",
                        "description": (
                            "Filter events starting before date (YYYY-MM-DD)"
                        ),
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category (e.g., Sports, Arts)",
                    },
                    "neighborhood": {
                        "type": "string",
                        "description": "Filter by neighborhood",
                    },
                    "latitude": {
                        "type": "number",
                        "description": "Center latitude for proximity search",
                    },
                    "longitude": {
                        "type": "number",
                        "description": "Center longitude for proximity search",
                    },
                    "radius_km": {
                        "type": "number",
                        "description": "Search radius in km",
                        "default": 5.0,
                    },
                    "search": {
                        "type": "string",
                        "description": (
                            "Free-text search across event name, description, "
                            "and location"
                        ),
                    },
                    "relative_date": {
                        "type": "string",
                        "description": (
                            "Relative date keyword (e.g., tomorrow, today, weekend)"
                        ),
                    },
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
    limit = _clamp_limit(arguments.get("limit", DEFAULT_LIMIT))
    start_date_from = arguments.get("start_date_from")
    start_date_to = arguments.get("start_date_to")
    end_date_from = arguments.get("end_date_from")
    end_date_to = arguments.get("end_date_to")
    latitude = _to_float(arguments.get("latitude"))
    longitude = _to_float(arguments.get("longitude"))
    radius_km = _to_float(arguments.get("radius_km", 5.0)) or 5.0
    if radius_km <= 0:
        radius_km = 5.0
    category = arguments.get("category")
    neighborhood = arguments.get("neighborhood")
    search = arguments.get("search")
    relative_date = arguments.get("relative_date") or arguments.get("date_keyword")

    if isinstance(search, str):
        normalized_search = search
        search_lower = search.lower()
        for keyword in sorted(RELATIVE_DATE_KEYWORDS, key=len, reverse=True):
            if keyword in search_lower:
                relative_date = relative_date or RELATIVE_DATE_KEYWORDS[keyword]
                pattern = re.compile(rf"\\b{re.escape(keyword)}\\b", re.IGNORECASE)
                normalized_search = pattern.sub(" ", normalized_search)
        search = " ".join(normalized_search.split()) or None
    use_cache_arg = arguments.get("use_cache", True)
    if isinstance(use_cache_arg, str):
        use_cache = use_cache_arg.strip().lower() not in {"false", "0", "no"}
    else:
        use_cache = bool(use_cache_arg)

    fetch_limit = min(MAX_FETCH_LIMIT, max(limit * FETCH_LIMIT_MULTIPLIER, limit))

    logger.info("Request arguments: %s", arguments)

    # Create cache key for the fetched dataset (search handled locally)
    cache_key = _make_cache_key(limit=fetch_limit)

    # Try to get from cache
    payload = None
    from_cache = False
    if use_cache and cache_key in api_cache:
        payload = api_cache[cache_key]
        from_cache = True
        logger.info("Cache hit for key: %s", cache_key)

    # Fetch from API if not in cache
    if payload is None:
        params: dict[str, Any] = {
            "$limit": fetch_limit,
            "$order": "event_start_date ASC",
        }

        logger.info("Fetching SF Rec & Park events from API with params: %s", params)

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
                logger.info("Cache set for key: %s", cache_key)
        except Exception as e:
            logger.error("API error: %s", e)
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
            neighborhood=neighborhood,
            search=search,
            relative_date=relative_date,
        )

        event_cards = [format_event_card(event) for event in filtered_payload[:limit]]

        markers = _build_map_markers(event_cards)
        map_data = {
            'markers': markers,
            'center': _average_coordinates(event_cards) or DEFAULT_CITY_CENTER,
            'defaultCenter': DEFAULT_CITY_CENTER,
            'markerCount': len(markers)
        }

        structured_content = {
            'summary': {
                'total_found': len(filtered_payload),
                'showing': len(event_cards),
                'from_cache': from_cache
            },
            'events': event_cards,
            'map': map_data,
        }
    else:
        structured_content = {
            'summary': {
                'total_found': 0,
                'showing': 0,
                'from_cache': from_cache
            },
            'events': [],
            'map': {
                'markers': [],
                'center': DEFAULT_CITY_CENTER,
                'defaultCenter': DEFAULT_CITY_CENTER,
                'markerCount': 0
            }
        }

    logger.info("Response summary: %s", structured_content.get('summary'))

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

    events_found = structured_content['summary']['showing']
    message = (
        f"Found {events_found} SF Recreation & Parks events!"
    )

    return types.ServerResult(
        types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=message,
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
