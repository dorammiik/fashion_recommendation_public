import React from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { LiveAPI } from './api';
import { MockAPI } from './mock';
import { Store } from './store';
import './style.css';
// Published builds always use the real API, including bare URLs and old mock links.
const live = import.meta.env.PROD || new URLSearchParams(location.search).get('mode') === 'live';
const mock = live ? undefined : new MockAPI();
const api = mock || new LiveAPI((import.meta.env.VITE_API_BASE_URL || (import.meta.env.PROD ? '/' : 'http://127.0.0.1:8765')).replace(/\/$/, ''));
const mode = live ? 'live' : 'mock';
let freshEntry = false;
try {
  freshEntry = sessionStorage.getItem('fashion.ui.mode-entry') === mode;
  if (freshEntry) sessionStorage.removeItem('fashion.ui.mode-entry');
} catch { /* Store reports unavailable persistence separately. */ }
const store = new Store(api, sessionStorage, `fashion.ui.v1.${mode}`, live ? 5000 : 750, freshEntry);
createRoot(document.getElementById('root')!).render(<App store={store} mock={mock}/>);
