import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { App } from './App';
import { Prototype } from './prototype/Prototype';

const params = new URLSearchParams(window.location.search);

createRoot(document.getElementById('root')!).render(
  <StrictMode>{params.get('proto') === '1' ? <Prototype /> : <App />}</StrictMode>,
);
