import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { api } from './api/client'
import './index.css'

// Set API key from build-time env var (for Vite dev server).
// In Docker production, users authenticate via JWT login flow,
// so this is only needed for local `bun run dev`.
if (import.meta.env.VITE_API_KEY) {
  api.setApiKey(import.meta.env.VITE_API_KEY as string)
}

window.addEventListener('unhandledrejection', (event: PromiseRejectionEvent) => {
  if (event.reason instanceof Error) {
    console.error(
      `[Unhandled Rejection] ${event.reason.name}: ${event.reason.message}`,
      event.reason,
    )
  } else {
    console.error('[Unhandled Rejection]', event.reason)
  }
  event.preventDefault()
})

window.addEventListener('error', (event: ErrorEvent) => {
  console.error(
    `[Uncaught Error] ${event.message} at ${event.filename}:${event.lineno}:${event.colno}`,
    event.error,
  )
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
