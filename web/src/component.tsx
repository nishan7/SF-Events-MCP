import React from 'react';
import { createRoot } from 'react-dom/client';
import EventsApp from './EventsApp';

// Mount the component when the DOM is ready
const root = document.getElementById('root');
if (root) {
  createRoot(root).render(<EventsApp />);
}
