import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'
import { api } from './api/client'
import '@xyflow/react/dist/style.css'
import './index.css'

// Set API key from environment variable (or default for development)
api.setApiKey(import.meta.env.VITE_API_KEY || 'change-me-in-production')

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
