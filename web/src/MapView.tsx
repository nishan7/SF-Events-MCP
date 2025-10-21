import React, { useEffect, useRef, useState } from 'react';
import { useToolOutput, useTheme } from './hooks';
import mapboxgl from 'mapbox-gl';
import 'mapbox-gl/dist/mapbox-gl.css';

// Free public Mapbox token for development
mapboxgl.accessToken = 'pk.eyJ1IjoiZXJpY25pbmciLCJhIjoiY21icXlubWM1MDRiczJvb2xwM2p0amNyayJ9.n-3O6JI5nOp_Lw96ZO5vJQ';

interface EventCard {
  title: string;
  dates: {
    start: string;
    end: string;
  };
  category: string;
  location: {
    name: string;
    neighborhood: string;
    address: string;
  };
  distance_km?: number;
  description?: string;
  registration_url?: string;
  coordinates?: {
    lat: number;
    lng: number;
  };
}

interface EventsResponse {
  summary: {
    total_found: number;
    showing: number;
    from_cache: boolean;
  };
  events: EventCard[];
}

export default function MapView() {
  const toolOutput = useToolOutput() as EventsResponse | null;
  const theme = useTheme();
  const isDark = theme === 'dark';
  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<mapboxgl.Marker[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventCard | null>(null);
  const popupRef = useRef<mapboxgl.Popup | null>(null);

  const containerStyle: React.CSSProperties = {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    padding: '16px',
    maxWidth: '1200px',
    margin: '0 auto',
    color: isDark ? '#e0e0e0' : '#1a1a1a',
  };

  const headerStyle: React.CSSProperties = {
    marginBottom: '20px',
    paddingBottom: '12px',
    borderBottom: `2px solid ${isDark ? '#333' : '#e5e5e5'}`,
  };

  const mapContainerStyle: React.CSSProperties = {
    position: 'relative',
    width: '100%',
    height: '600px',
    borderRadius: '12px',
    overflow: 'hidden',
    marginBottom: '20px',
  };

  const eventCardStyle: React.CSSProperties = {
    backgroundColor: isDark ? '#1e1e1e' : '#ffffff',
    border: `1px solid ${isDark ? '#333' : '#e5e5e5'}`,
    borderRadius: '12px',
    padding: '16px',
    boxShadow: isDark
      ? '0 2px 8px rgba(0,0,0,0.3)'
      : '0 2px 8px rgba(0,0,0,0.1)',
  };

  // Initialize map
  useEffect(() => {
    if (!mapRef.current || mapInstance.current) return;

    const map = new mapboxgl.Map({
      container: mapRef.current,
      style: isDark ? 'mapbox://styles/mapbox/dark-v11' : 'mapbox://styles/mapbox/streets-v12',
      center: [-122.4194, 37.7749], // San Francisco
      zoom: 12,
    });

    map.addControl(new mapboxgl.NavigationControl(), 'top-right');
    map.addControl(new mapboxgl.FullscreenControl(), 'top-right');

    mapInstance.current = map;

    return () => {
      map.remove();
      mapInstance.current = null;
    };
  }, [isDark]);

  // Add markers for events
  useEffect(() => {
    if (!mapInstance.current || !toolOutput?.events) return;

    // Clear existing markers
    markersRef.current.forEach(marker => marker.remove());
    markersRef.current = [];

    const eventsWithCoords = toolOutput.events.filter(e => e.coordinates);

    if (eventsWithCoords.length === 0) return;

    // Add markers
    eventsWithCoords.forEach((event) => {
      const el = document.createElement('div');
      el.style.width = '30px';
      el.style.height = '30px';
      el.style.borderRadius = '50% 50% 50% 0';
      el.style.backgroundColor = '#1976d2';
      el.style.border = '2px solid white';
      el.style.transform = 'rotate(-45deg)';
      el.style.cursor = 'pointer';
      el.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';

      const marker = new mapboxgl.Marker({ element: el })
        .setLngLat([event.coordinates!.lng, event.coordinates!.lat])
        .addTo(mapInstance.current!);

      el.addEventListener('click', () => {
        setSelectedEvent(event);

        // Close existing popup
        if (popupRef.current) {
          popupRef.current.remove();
        }

        // Create popup content
        const popupContent = document.createElement('div');
        popupContent.innerHTML = `
          <div style="padding: 8px; max-width: 250px;">
            <h3 style="margin: 0 0 8px 0; font-size: 16px; font-weight: 600;">
              ${event.category ? getCategoryEmoji(event.category) + ' ' : ''}${event.title}
            </h3>
            <div style="font-size: 14px; color: #666; margin-bottom: 8px;">
              📍 ${event.location.name}${event.location.neighborhood ? ` (${event.location.neighborhood})` : ''}
            </div>
            ${event.distance_km ? `
              <div style="font-size: 14px; color: #666; margin-bottom: 8px;">
                📏 ${(event.distance_km * 0.621371).toFixed(2)} miles away
              </div>
            ` : ''}
            ${event.registration_url ? `
              <button id="info-btn-${event.coordinates!.lat}" style="
                margin-top: 8px;
                padding: 8px 16px;
                background-color: #1976d2;
                color: white;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-weight: 500;
              ">More Info ↗</button>
            ` : ''}
          </div>
        `;

        const popup = new mapboxgl.Popup({ offset: 25 })
          .setLngLat([event.coordinates!.lng, event.coordinates!.lat])
          .setDOMContent(popupContent)
          .addTo(mapInstance.current!);

        popupRef.current = popup;

        // Add event listener to button
        if (event.registration_url) {
          setTimeout(() => {
            const btn = document.getElementById(`info-btn-${event.coordinates!.lat}`);
            if (btn) {
              btn.addEventListener('click', () => {
                window.openai?.openExternal({ href: event.registration_url! });
              });
            }
          }, 0);
        }

        // Highlight marker
        el.style.backgroundColor = '#f44336';
        el.style.width = '36px';
        el.style.height = '36px';

        popup.on('close', () => {
          el.style.backgroundColor = '#1976d2';
          el.style.width = '30px';
          el.style.height = '30px';
        });
      });

      markersRef.current.push(marker);
    });

    // Fit map to markers
    if (eventsWithCoords.length > 0) {
      const bounds = new mapboxgl.LngLatBounds();
      eventsWithCoords.forEach(event => {
        bounds.extend([event.coordinates!.lng, event.coordinates!.lat]);
      });
      mapInstance.current.fitBounds(bounds, { padding: 60, maxZoom: 14 });
    }
  }, [toolOutput, isDark]);

  function getCategoryEmoji(category: string): string {
    if (category.includes('Sport')) return '⚽';
    if (category.includes('Art')) return '🎨';
    if (category.includes('Class')) return '📚';
    if (category.includes('Camp')) return '⛺';
    return '📅';
  }

  if (!toolOutput) {
    return (
      <div style={containerStyle}>
        <p style={{ textAlign: 'center', color: isDark ? '#999' : '#666' }}>
          Loading events...
        </p>
      </div>
    );
  }

  const { summary, events } = toolOutput;
  const eventsWithCoords = events.filter(e => e.coordinates);

  if (eventsWithCoords.length === 0) {
    return (
      <div style={containerStyle}>
        <div style={headerStyle}>
          <h2 style={{ margin: '0 0 8px 0', fontSize: '24px', fontWeight: '600' }}>
            SF Recreation & Parks Events - Map View
          </h2>
        </div>
        <p style={{ textAlign: 'center', color: isDark ? '#999' : '#666' }}>
          No events with location data available.
        </p>
      </div>
    );
  }

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <h2 style={{ margin: '0 0 8px 0', fontSize: '24px', fontWeight: '600' }}>
          🗺️ SF Recreation & Parks Events
        </h2>
        <div style={{ fontSize: '14px', color: isDark ? '#b0b0b0' : '#666' }}>
          Showing {eventsWithCoords.length} events on map
        </div>
      </div>

      <div ref={mapRef} style={mapContainerStyle} />

      {/* Event list below map */}
      <div style={{ marginTop: '20px' }}>
        <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '12px' }}>
          Events on Map
        </h3>
        <div style={{ display: 'grid', gap: '12px' }}>
          {eventsWithCoords.map((event, index) => (
            <div
              key={index}
              style={{
                ...eventCardStyle,
                cursor: 'pointer',
                border: selectedEvent === event
                  ? `2px solid ${isDark ? '#90caf9' : '#1976d2'}`
                  : `1px solid ${isDark ? '#333' : '#e5e5e5'}`,
              }}
              onClick={() => {
                if (mapInstance.current && event.coordinates) {
                  mapInstance.current.flyTo({
                    center: [event.coordinates.lng, event.coordinates.lat],
                    zoom: 15,
                  });
                  setSelectedEvent(event);
                }
              }}
            >
              <div style={{ fontSize: '16px', fontWeight: '600', marginBottom: '4px' }}>
                {event.category && (
                  <span style={{ marginRight: '8px' }}>
                    {getCategoryEmoji(event.category)}
                  </span>
                )}
                {event.title}
              </div>
              <div style={{ fontSize: '14px', color: isDark ? '#b0b0b0' : '#666' }}>
                {event.location.name}
                {event.location.neighborhood && ` (${event.location.neighborhood})`}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
