import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { applyTheme, type Theme } from './state/themeStore'

function readInitialTheme(): Theme {
  try {
    const stored = localStorage.getItem('protdap.theme.v1')
    if (stored === 'light' || stored === 'dark') return stored
  } catch {
    // localStorage may be unavailable.
  }
  return 'light'
}

applyTheme(readInitialTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
