import React from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource-variable/golos-text';
import '@fontsource-variable/unbounded';
import './styles/globals.css';
import App from './App';
import { captureTelegramInitParams, loadTelegramSdk, setupTelegramTheme } from './telegram/webapp';

const container = document.getElementById('root');
if (!container) throw new Error('#root not found');

captureTelegramInitParams();
setupTelegramTheme();
void loadTelegramSdk().then(setupTelegramTheme);

createRoot(container).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
