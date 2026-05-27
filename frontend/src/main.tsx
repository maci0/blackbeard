import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { api } from './api/client'
import '@xyflow/react/dist/style.css'
import './index.css'

// Set API key from build-time env var (for Vite dev server).
// In Docker production, nginx injects the key server-side (NGINX_API_KEY_FALLBACK)
// so this is only needed for local `bun run dev`.
if (import.meta.env.VITE_API_KEY) {
  api.setApiKey(import.meta.env.VITE_API_KEY as string)
}

window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  console.error('[Unhandled Rejection]', event.reason)
  event.preventDefault()
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
