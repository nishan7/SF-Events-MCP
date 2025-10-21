"""Single-file FastMCP server exposing SF Rec & Park event data."""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from typing import Any
from datetime import datetime, date
from math import radians, sin, cos, sqrt, atan2

import httpx
from dotenv import load_dotenv
from cachetools import TTLCache

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
)

# Initialize TTL cache: max 100 items, 5-minute (300 seconds) TTL
api_cache = TTLCache(maxsize=100, ttl=300)


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

        a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
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


@mcp.tool("fetch_rec_events")
async def fetch_rec_events(
    limit: int = 5,
    start_date_from: str | None = None,
    start_date_to: str | None = None,
    end_date_from: str | None = None,
    end_date_to: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float = 5.0,
    category: str | None = None,
    neighborhood: str | None = None,
    use_cache: bool = True
) -> dict[str, Any]:
    """Retrieve upcoming Recreation & Parks events.

    Args:
        limit: Maximum number of events to retrieve (1-100)
        start_date_from: Filter events starting from this date (YYYY-MM-DD format)
        start_date_to: Filter events starting before this date (YYYY-MM-DD format)
        end_date_from: Filter events ending from this date (YYYY-MM-DD format)
        end_date_to: Filter events ending before this date (YYYY-MM-DD format)
        latitude: Center latitude for proximity search
        longitude: Center longitude for proximity search
        radius_km: Maximum distance in kilometers (default: 5.0)
        category: Filter by event category (case-insensitive partial match)
        neighborhood: Filter by neighborhood (case-insensitive partial match)
        use_cache: Whether to use cached data if available (default: True)
    """
    bounded_limit = limit

    # Create cache key based on limit
    cache_key = f"events_limit_{bounded_limit}"

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

        await get_context().info(os.getenv('APPTOKEN'))
        logger.info("Fetching SF Rec & Park events from API", extra={"params": params})

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(API_URL, params=params,
                                        headers={"Accept": "application/json",
                                                 'X-App-Token': os.getenv('APPTOKEN', 'STkpW9v5bxHaghK4Y5nmp3BzC')})
            response.raise_for_status()
            payload = response.json()

        # Store in cache
        if payload and len(payload) > 0:
            api_cache[cache_key] = payload
            logger.info(f"Cache set for key: {cache_key}")

    if payload and len(payload) > 0:
        # Apply client-side filtering using EventFilter class
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

        return {
            'total_fetched': len(payload),
            'total_after_filter': len(filtered_payload),
            'from_cache': from_cache,
            'filters_applied': {
                'date': any([start_date_from, start_date_to, end_date_from, end_date_to]),
                'location': latitude is not None and longitude is not None,
                'category': category is not None,
                'neighborhood': neighborhood is not None
            },
            'events': filtered_payload[:bounded_limit]
        }
    else:
        return {
            'total_fetched': 0,
            'total_after_filter': 0,
            'from_cache': from_cache,
            'filters_applied': {},
            'events': []
        }


@mcp.tool("clear_cache")
async def clear_cache() -> dict[str, str]:
    """Clear the API cache manually."""
    api_cache.clear()
    logger.info("Cache cleared")
    return {'status': 'success', 'message': 'Cache cleared successfully'}


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    mcp.run(transport="http", port=8000)
