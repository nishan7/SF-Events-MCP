"""Filtering utilities for SF Recreation & Parks events."""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from math import atan2, cos, radians, sin, sqrt
from typing import Any

from .config import RELATIVE_DATE_KEYWORDS

logger = logging.getLogger("fastmcp.sfevents.filtering")


class EventFilter:
    """Filter events by various criteria."""

    @staticmethod
    def parse_date_string(date_str: str) -> date | None:
        """Parse a date string in various formats to a date object."""
        if not date_str:
            return None

        try:
            if "T" in date_str:
                return datetime.fromisoformat(date_str.split(".")[0]).date()
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, AttributeError):
            logger.debug("Failed to parse date: %s", date_str)
            return None

    @staticmethod
    def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the distance between two coordinates using the Haversine formula."""
        earth_radius_km = 6371.0

        lat1_rad = radians(lat1)
        lon1_rad = radians(lon1)
        lat2_rad = radians(lat2)
        lon2_rad = radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat / 2) ** 2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        return earth_radius_km * c

    @classmethod
    def filter_by_date(
        cls,
        events: list[dict[str, Any]],
        start_date_from: str | None = None,
        start_date_to: str | None = None,
        end_date_from: str | None = None,
        end_date_to: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter events by date ranges after fetching from the API."""
        if not any([start_date_from, start_date_to, end_date_from, end_date_to]):
            return events

        filter_start_from = cls.parse_date_string(start_date_from) if start_date_from else None
        filter_start_to = cls.parse_date_string(start_date_to) if start_date_to else None
        filter_end_from = cls.parse_date_string(end_date_from) if end_date_from else None
        filter_end_to = cls.parse_date_string(end_date_to) if end_date_to else None

        filtered_events: list[dict[str, Any]] = []

        for event in events:
            event_start = cls.parse_date_string(event.get("event_start_date", ""))
            event_end = cls.parse_date_string(event.get("event_end_date", ""))

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
        radius_km: float = 5.0,
    ) -> list[dict[str, Any]]:
        """Filter events by proximity to coordinates."""
        if latitude is None or longitude is None:
            return events

        filtered_events: list[dict[str, Any]] = []

        for event in events:
            try:
                event_lat = float(event.get("latitude", 0))
                event_lon = float(event.get("longitude", 0))
            except (ValueError, TypeError):
                logger.debug("Failed to parse coordinates for event: %s", event)
                continue

            if not event_lat or not event_lon:
                continue

            distance = cls.calculate_distance(latitude, longitude, event_lat, event_lon)
            if distance <= radius_km:
                event_copy = event.copy()
                event_copy["distance_km"] = round(distance, 2)
                filtered_events.append(event_copy)

        filtered_events.sort(key=lambda item: item.get("distance_km", float("inf")))
        return filtered_events

    @staticmethod
    def filter_by_category(
        events: list[dict[str, Any]],
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter events by category (case-insensitive partial match)."""
        if not category:
            return events

        category_lower = category.lower()
        return [
            event
            for event in events
            if category_lower in (event.get("events_category", "") or "").lower()
        ]

    @staticmethod
    def filter_by_neighborhood(
        events: list[dict[str, Any]],
        neighborhood: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter events by neighborhood (case-insensitive partial match)."""
        if not neighborhood:
            return events

        neighborhood_lower = neighborhood.lower()
        return [
            event
            for event in events
            if neighborhood_lower in (event.get("analysis_neighborhood", "") or "").lower()
        ]

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
        """Apply all available filters to the events list."""
        filtered = cls.filter_upcoming(events)

        if relative_date:
            start_from, start_to = cls.relative_date_window(relative_date)
            if start_from and start_to:
                start_date_from = start_date_from or start_from
                start_date_to = start_date_to or start_to

        filtered = cls.filter_by_date(
            filtered,
            start_date_from=start_date_from,
            start_date_to=start_date_to,
            end_date_from=end_date_from,
            end_date_to=end_date_to,
        )
        filtered = cls.filter_by_category(filtered, category=category)
        filtered = cls.filter_by_neighborhood(filtered, neighborhood=neighborhood)
        filtered = cls.filter_by_search(filtered, search=search)
        filtered = cls.filter_by_location(
            filtered,
            latitude=latitude,
            longitude=longitude,
            radius_km=radius_km,
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
            return today.isoformat(), today.isoformat()
        if keyword_normalized in {"tomorrow", "tmrw"}:
            target = today + timedelta(days=1)
            return target.isoformat(), target.isoformat()
        if keyword_normalized in {"weekend", "this weekend"}:
            saturday_offset = (5 - today.weekday()) % 7
            saturday = today + timedelta(days=saturday_offset)
            sunday = saturday + timedelta(days=1)
            return saturday.isoformat(), sunday.isoformat()

        mapped = RELATIVE_DATE_KEYWORDS.get(keyword_normalized)
        if mapped and mapped != keyword_normalized:
            return EventFilter.relative_date_window(mapped)

        return None, None

    @staticmethod
    def filter_by_search(
        events: list[dict[str, Any]],
        search: str | None = None,
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

            if query in haystack or EventFilter._fuzzy_match(query, tokens, haystack):
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
