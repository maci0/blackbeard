import { useState, useEffect } from 'react'
import { Save, ExternalLink } from 'lucide-react'
import { useDocumentTitle } from '@/hooks'
import { PageHeader } from '@/components/ui/PageHeader'
import { useToastStore } from '@/stores/toastStore'

interface PublicConfig {
  oidc_enabled: boolean
}

export default function Settings() {
  useDocumentTitle('Settings')

  const [apiBase, setApiBase] = useState(() => localStorage.getItem('blackbeard_api_base') || '')
  const [config, setConfig] = useState<PublicConfig | null>(null)

  useEffect(() => {
    fetch('/api/v1/config/public')
      .then((r) => r.json())
      .then((d: PublicConfig) => setConfig(d))
      .catch(() => {})
  }, [])

  const handleSaveApiBase = () => {
    const trimmed = apiBase.trim()
    if (trimmed) {
      localStorage.setItem('blackbeard_api_base', trimmed)
    } else {
      localStorage.removeItem('blackbeard_api_base')
    }
    useToastStore.getState().success('API base URL saved. Reload the page to apply.')
  }

  return (
    <div className="mx-auto max-w-3xl space-y-8 p-6">
      <PageHeader title="Settings" description="Configure your Blackbeard instance" />

      {/* API Connection */}
      <section className="space-y-4 rounded-lg border p-5">
        <h2 className="text-sm font-semibold">API Connection</h2>
        <p className="text-xs text-muted-foreground">
          Override the API base URL if the backend runs on a different host. Leave empty to use the
          default (same origin via proxy).
        </p>
        <div className="flex gap-2">
          <input
            type="url"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder="http://localhost:8000 (default)"
            className="flex-1 rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            aria-label="API base URL"
          />
          <button
            onClick={handleSaveApiBase}
            className="flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90"
            title="Save API base URL"
          >
            <Save className="h-3.5 w-3.5" />
            Save
          </button>
        </div>
      </section>

      {/* Service Status */}
      <section className="space-y-4 rounded-lg border p-5">
        <h2 className="text-sm font-semibold">Services</h2>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">API Server</span>
            <a
              href="/api/v1/health"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-primary hover:underline"
              title="Open API health endpoint"
            >
              /api/v1/health <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">LiteLLM Proxy</span>
            <a
              href="http://localhost:4000/ui"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-primary hover:underline"
              title="Open LiteLLM dashboard"
            >
              :4000/ui <ExternalLink className="h-3 w-3" />
            </a>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">OpenAPI Docs</span>
            <a
              href="/api/v1/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-1 text-xs text-primary hover:underline"
              title="Open API documentation"
            >
              /api/v1/docs <ExternalLink className="h-3 w-3" />
            </a>
          </div>
        </div>
      </section>

      {/* Authentication */}
      <section className="space-y-4 rounded-lg border p-5">
        <h2 className="text-sm font-semibold">Authentication</h2>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">SSO / OIDC</span>
            <span
              className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${
                config?.oidc_enabled
                  ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-400'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              {config?.oidc_enabled ? 'Enabled' : 'Not configured'}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Auth method</span>
            <span className="text-xs font-medium">
              {config?.oidc_enabled ? 'OIDC + Email/Password' : 'Email/Password + API Key'}
            </span>
          </div>
        </div>
      </section>

      {/* About */}
      <section className="space-y-4 rounded-lg border p-5">
        <h2 className="text-sm font-semibold">About</h2>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Version</span>
            <span className="font-mono text-xs">v0.1.0</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Resource kinds</span>
            <span className="text-xs font-medium">13</span>
          </div>
        </div>
      </section>
    </div>
  )
}
