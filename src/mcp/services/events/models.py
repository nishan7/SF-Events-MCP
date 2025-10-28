"""Pydantic models describing event data returned by the FastMCP server."""

from __future__ import annotations

from collections.abc import Iterable

from pydantic import BaseModel, Field


class Coordinates(BaseModel):
    """Latitude/longitude pair."""

    lat: float
    lng: float

    @staticmethod
    def average(coords: Iterable[Coordinates]) -> Coordinates | None:
        items = list(coords)
        if not items:
            return None
        lat = sum(item.lat for item in items) / len(items)
        lng = sum(item.lng for item in items) / len(items)
        return Coordinates(lat=lat, lng=lng)


class EventDates(BaseModel):
    start: str | None = Field(default=None, description="Event start date time string")
    end: str | None = Field(default=None, description="Event end date time string")


class EventLocation(BaseModel):
    name: str = ""
    neighborhood: str | None = None
    address: str | None = None


class EventCard(BaseModel):
    title: str
    dates: EventDates
    category: str | None = None
    location: EventLocation
    distance_km: float | None = None
    coordinates: Coordinates | None = None
    description: str | None = None
    details_url: str | None = None
    registration_url: str | None = None
    more_info: str | None = None


class MapMarker(BaseModel):
    title: str = ""
    category: str | None = None
    coordinates: Coordinates
    location: EventLocation | None = None
    details_url: str | None = None

    @classmethod
    def from_event(cls, event: EventCard) -> MapMarker | None:
        if event.coordinates is None:
            return None
        return cls(
            title=event.title,
            category=event.category,
            coordinates=event.coordinates,
            location=event.location,
            details_url=event.details_url or event.registration_url,
        )


class MapData(BaseModel):
    markers: list[MapMarker]
    center: Coordinates
    default_center: Coordinates
    marker_count: int


class SearchSummary(BaseModel):
    total_found: int
    showing: int
    from_cache: bool


class SearchResponse(BaseModel):
    summary: SearchSummary
    events: list[EventCard]
    map: MapData
