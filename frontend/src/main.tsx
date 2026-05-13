import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { api } from './api/client'
import '@xyflow/react/dist/style.css'
import './index.css'

// Set API key from environment variable — no hardcoded fallback.
// In development, set VITE_API_KEY in .env.local or the browser will send
// requests without an API key (which the backend rejects with 401).
if (import.meta.env.VITE_API_KEY) {
  api.setApiKey(import.meta.env.VITE_API_KEY)
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
