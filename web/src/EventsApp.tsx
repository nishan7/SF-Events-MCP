import React, { useState } from 'react';
import { useTheme } from './hooks';
import SFEventsComponent from './EventsUI';
import MapView from './MapView';

export default function EventsApp() {
  const [view, setView] = useState<'cards' | 'map'>('cards');
  const theme = useTheme();
  const isDark = theme === 'dark';

  const containerStyle: React.CSSProperties = {
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  };

  const toggleContainerStyle: React.CSSProperties = {
    display: 'flex',
    justifyContent: 'center',
    padding: '16px',
    gap: '8px',
  };

  const buttonStyle = (isActive: boolean): React.CSSProperties => ({
    padding: '10px 24px',
    fontSize: '14px',
    fontWeight: '500',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    backgroundColor: isActive
      ? (isDark ? '#2a4a6a' : '#1976d2')
      : (isDark ? '#333' : '#e5e5e5'),
    color: isActive
      ? '#ffffff'
      : (isDark ? '#b0b0b0' : '#666'),
    transition: 'all 0.2s',
  });

  return (
    <div style={containerStyle}>
      <div style={toggleContainerStyle}>
        <button
          style={buttonStyle(view === 'cards')}
          onClick={() => setView('cards')}
        >
          📋 Card View
        </button>
        <button
          style={buttonStyle(view === 'map')}
          onClick={() => setView('map')}
        >
          🗺️ Map View
        </button>
      </div>

      {view === 'cards' ? <SFEventsComponent /> : <MapView />}
    </div>
  );
}

