import React from 'react';
import { useToolOutput, useTheme } from './hooks';
import Logo from './Logo';

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
  details_url?: string;
  more_info?: string;
  coordinates?: {
    lat: number;
    lng: number;
  };
}

interface EventMapData {
  markers: Array<{
    title?: string;
    category?: string;
    coordinates?: {
      lat: number;
      lng: number;
    };
    location?: {
      name?: string;
      neighborhood?: string;
      address?: string;
    };
    details_url?: string;
  }>;
  center: {
    lat: number;
    lng: number;
  };
  defaultCenter: {
    lat: number;
    lng: number;
  };
  markerCount: number;
}

interface EventsResponse {
  summary: {
    total_found: number;
    showing: number;
    from_cache: boolean;
  };
  events: EventCard[];
  map?: EventMapData;
}

function formatDate(dateStr: string): string {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  } catch {
    return dateStr;
  }
}

function EventCardComponent({ event }: { event: EventCard }) {
  const theme = useTheme();
  const isDark = theme === 'dark';
  const detailsUrl = event.details_url || event.registration_url || event.more_info;

  const cardStyle: React.CSSProperties = {
    backgroundColor: isDark ? '#1e1e1e' : '#ffffff',
    border: `1px solid ${isDark ? '#333' : '#e5e5e5'}`,
    borderRadius: '12px',
    padding: '20px',
    marginBottom: '16px',
    boxShadow: isDark
      ? '0 2px 8px rgba(0,0,0,0.3)'
      : '0 2px 8px rgba(0,0,0,0.1)',
    cursor: detailsUrl ? 'pointer' : 'default',
    transition: 'transform 0.2s, box-shadow 0.2s',
  };

  const handleCardClick = () => {
    if (detailsUrl) {
      window.openai?.openExternal({ href: detailsUrl });
    }
  };

  const titleStyle: React.CSSProperties = {
    fontSize: '18px',
    fontWeight: '600',
    marginBottom: '12px',
    color: isDark ? '#ffffff' : '#1a1a1a',
  };

  const categoryStyle: React.CSSProperties = {
    display: 'inline-block',
    backgroundColor: isDark ? '#2a4a6a' : '#e3f2fd',
    color: isDark ? '#90caf9' : '#1976d2',
    padding: '4px 12px',
    borderRadius: '16px',
    fontSize: '12px',
    fontWeight: '500',
    marginBottom: '12px',
  };

  const sectionStyle: React.CSSProperties = {
    marginBottom: '10px',
    color: isDark ? '#e0e0e0' : '#333',
    fontSize: '14px',
    lineHeight: '1.6',
  };

  const labelStyle: React.CSSProperties = {
    fontWeight: '600',
    color: isDark ? '#b0b0b0' : '#666',
    marginRight: '6px',
  };

  const linkStyle: React.CSSProperties = {
    color: isDark ? '#90caf9' : '#1976d2',
    textDecoration: 'none',
    fontWeight: '500',
  };

  return (
    <div
      style={cardStyle}
      onClick={handleCardClick}
      onMouseEnter={(e) => {
        if (detailsUrl) {
          e.currentTarget.style.transform = 'translateY(-2px)';
          e.currentTarget.style.boxShadow = isDark
            ? '0 4px 12px rgba(0,0,0,0.4)'
            : '0 4px 12px rgba(0,0,0,0.15)';
        }
      }}
      onMouseLeave={(e) => {
        if (detailsUrl) {
          e.currentTarget.style.transform = 'translateY(0)';
          e.currentTarget.style.boxShadow = isDark
            ? '0 2px 8px rgba(0,0,0,0.3)'
            : '0 2px 8px rgba(0,0,0,0.1)';
        }
      }}
    >
      <div style={titleStyle}>
        {event.category && <span style={{ marginRight: '8px' }}>
          {event.category.includes('Sport') ? '⚽' :
           event.category.includes('Art') ? '🎨' :
           event.category.includes('Class') ? '📚' :
           event.category.includes('Camp') ? '⛺' : '📅'}
        </span>}
        {event.title}
      </div>

      {event.category && (
        <div style={{ marginBottom: '12px' }}>
          <span style={categoryStyle}>{event.category}</span>
        </div>
      )}

      {event.dates && (
        <div style={sectionStyle}>
          <span style={labelStyle}>When:</span>
          {formatDate(event.dates.start)}
          {event.dates.end && event.dates.end !== event.dates.start &&
            ` – ${formatDate(event.dates.end)}`}
        </div>
      )}

      {event.location && (
        <div style={sectionStyle}>
          <span style={labelStyle}>Where:</span>
          {event.location.name}
          {event.location.neighborhood && ` (${event.location.neighborhood})`}
        </div>
      )}

      {event.description && (
        <div style={sectionStyle}>
          <span style={labelStyle}>Details:</span>
          {event.description}
        </div>
      )}

      {detailsUrl && (
        <div style={{ marginTop: '12px' }}>
          <a
            href={detailsUrl}
            style={linkStyle}
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              window.openai?.openExternal({ href: detailsUrl });
            }}
          >
            More Info ↗
          </a>
        </div>
      )}
    </div>
  );
}

export default function SFEventsComponent() {
  const toolOutput = useToolOutput() as EventsResponse | null;
  const theme = useTheme();
  const isDark = theme === 'dark';

  const containerStyle: React.CSSProperties = {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    padding: '16px',
    maxWidth: '800px',
    margin: '0 auto',
    color: isDark ? '#e0e0e0' : '#1a1a1a',
  };

  const headerStyle: React.CSSProperties = {
    marginBottom: '20px',
    paddingBottom: '12px',
    borderBottom: `2px solid ${isDark ? '#333' : '#e5e5e5'}`,
  };

  const headerRowStyle: React.CSSProperties = {
    display: 'flex',
    alignItems: 'center',
    gap: '14px',
  };

  const summaryStyle: React.CSSProperties = {
    fontSize: '14px',
    color: isDark ? '#b0b0b0' : '#666',
    marginBottom: '8px',
  };

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

  return (
    <div style={containerStyle}>
      <div style={headerStyle}>
        <div style={headerRowStyle}>
          <Logo size={44} />
          <div>
            <h2 style={{ margin: '0 0 8px 0', fontSize: '24px', fontWeight: '600' }}>
              SF Recreation & Parks Events
            </h2>
            <div style={summaryStyle}>
              Showing {summary.showing} of {summary.total_found} events
              {summary.from_cache && ' (cached)'}
            </div>
          </div>
        </div>
      </div>

      {events.length === 0 ? (
        <p style={{ textAlign: 'center', color: isDark ? '#999' : '#666' }}>
          No events found matching your criteria.
        </p>
      ) : (
        events.map((event, index) => (
          <EventCardComponent key={index} event={event} />
        ))
      )}
    </div>
  );
}
