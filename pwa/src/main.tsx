import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import { initAnalytics } from './analytics'
import { getSettings } from './store'
import './styles.css'
import './motion.css'

initAnalytics(getSettings().userId)

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

if ('serviceWorker' in navigator) {
  navigator.serviceWorker.register('/sw.js').catch(() => {
    /* no service worker (plain http on a phone): the app works, but cannot be installed or receive shares */
  })
}
