import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import Lenis from 'lenis'

// ── Lenis Smooth Scrolling ──────────────────────────────────────────────────
// Attach Lenis to the .page-content scrollable container (not the whole window)
// so the sidebar and fixed bars are unaffected.
function initLenis() {
  const container = document.querySelector('.page-content');
  if (!container) {
    // Retry until the DOM is ready
    requestAnimationFrame(initLenis);
    return;
  }

  const lenis = new Lenis({
    wrapper: container,
    content: container,
    duration: 1.1,
    easing: (t) => Math.min(1, 1.001 - Math.pow(2, -10 * t)),
    orientation: 'vertical',
    smoothWheel: true,
    wheelMultiplier: 1,
    touchMultiplier: 2,
  });

  function raf(time) {
    lenis.raf(time);
    requestAnimationFrame(raf);
  }
  requestAnimationFrame(raf);
}

requestAnimationFrame(initLenis);
// ────────────────────────────────────────────────────────────────────────────

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
