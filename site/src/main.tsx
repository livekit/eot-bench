import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import App from './App';
import { applyTheme, RenderRoute, type RenderAsset } from './RenderRoute';
import './index.css';

const params = new URLSearchParams(window.location.search);
const render = params.get('render');

let root = <App />;
if (render === 'headline' || render === 'leaderboard') {
  const theme = params.get('theme') === 'dark' ? 'dark' : 'light';
  applyTheme(theme);
  root = <RenderRoute asset={render as RenderAsset} />;
}

createRoot(document.getElementById('root')!).render(<StrictMode>{root}</StrictMode>);
