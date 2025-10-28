"""Configuration constants for SF Recreation & Parks event services."""

from __future__ import annotations

API_URL = "https://data.sfgov.org/api/v3/views/8i3s-ih2a/query.json"

DEFAULT_LIMIT = 3
MAX_LIMIT = 25
FETCH_LIMIT_MULTIPLIER = 4
MAX_FETCH_LIMIT = 100

MIME_TYPE = "text/html+skybridge"
WIDGET_URI = "ui://widget/sf-events.html"
WIDGET_TITLE = "SF Events"

RELATIVE_DATE_KEYWORDS: dict[str, str] = {
    "today": "today",
    "tonight": "today",
    "tomorrow": "tomorrow",
    "tmrw": "tomorrow",
    "weekend": "weekend",
    "this weekend": "weekend",
}

DEFAULT_CITY_CENTER = {"lat": 37.7749, "lng": -122.4194}
