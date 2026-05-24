import { useState, useEffect } from 'react'
import { Save, ExternalLink, Key, Copy, RotateCw, Trash2, Eye, EyeOff } from 'lucide-react'
import { useDocumentTitle } from '@/hooks'
import { PageHeader } from '@/components/ui/PageHeader'
import { useToastStore } from '@/stores/toastStore'
import { api, ApiError } from '@/api/client'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'

interface PublicConfig {
  oidc_enabled: boolean
}

interface ApiKeyResponse {
  api_key: string
}

type ApiKeyStatus = 'unknown' | 'active' | 'none'

export default function Settings() {
  useDocumentTitle('Settings')

  const [apiBase, setApiBase] = useState(() => localStorage.getItem('blackbeard_api_base') || '')
  const [config, setConfig] = useState<PublicConfig | null>(null)

  const [keyStatus, setKeyStatus] = useState<ApiKeyStatus>('unknown')
  const [maskedKey, setMaskedKey] = useState('')
  const [revealedKey, setRevealedKey] = useState<string | null>(null)
  const [showKey, setShowKey] = useState(false)
  const [keyLoading, setKeyLoading] = useState(false)
  const [rotateOpen, setRotateOpen] = useState(false)
  const [revokeOpen, setRevokeOpen] = useState(false)

  useEffect(() => {
    fetch('/api/v1/config/public')
      .then((r) => r.json())
      .then((d: PublicConfig) => setConfig(d))
      .catch(() => {})
  }, [])

  useEffect(() => {
    setKeyLoading(true)
    api
      .get<{ has_key: boolean; masked_key?: string }>('/api/v1/auth/api-key')
      .then((res) => {
        if (res.has_key && res.masked_key) {
          setKeyStatus('active')
          setMaskedKey(res.masked_key)
        } else {
          setKeyStatus('none')
          setMaskedKey('')
        }
      })
      .catch((err: unknown) => {
        if (err instanceof ApiError && err.status === 404) {
          setKeyStatus('none')
        }
      })
      .finally(() => setKeyLoading(false))
  }, [])

  const handleGenerateKey = async () => {
    setKeyLoading(true)
    try {
      const res = await api.post<ApiKeyResponse>('/api/v1/auth/api-key', {})
      setRevealedKey(res.api_key)
      setShowKey(true)
      setKeyStatus('active')
      const key = res.api_key
      setMaskedKey(key.slice(0, 3) + '-' + '*'.repeat(4) + '...' + key.slice(-4))
      useToastStore.getState().success('API key generated successfully')
    } catch (err: unknown) {
      useToastStore
        .getState()
        .error(err instanceof ApiError ? err.message : 'Failed to generate API key')
    } finally {
      setKeyLoading(false)
    }
  }

  const handleRotateKey = async () => {
    setKeyLoading(true)
    try {
      const res = await api.post<ApiKeyResponse>('/api/v1/auth/api-key', {})
      setRevealedKey(res.api_key)
      setShowKey(true)
      const key = res.api_key
      setMaskedKey(key.slice(0, 3) + '-' + '*'.repeat(4) + '...' + key.slice(-4))
      setRotateOpen(false)
      useToastStore.getState().success('API key rotated successfully')
    } catch (err: unknown) {
      useToastStore
        .getState()
        .error(err instanceof ApiError ? err.message : 'Failed to rotate API key')
    } finally {
      setKeyLoading(false)
    }
  }

  const handleRevokeKey = async () => {
    setKeyLoading(true)
    try {
      await api.delete('/api/v1/auth/api-key')
      setKeyStatus('none')
      setMaskedKey('')
      setRevealedKey(null)
      setShowKey(false)
      setRevokeOpen(false)
      useToastStore.getState().success('API key revoked')
    } catch (err: unknown) {
      useToastStore
        .getState()
        .error(err instanceof ApiError ? err.message : 'Failed to revoke API key')
    } finally {
      setKeyLoading(false)
    }
  }

  const handleCopyKey = () => {
    if (!revealedKey) return
    void navigator.clipboard.writeText(revealedKey).then(() => {
      useToastStore.getState().success('API key copied to clipboard')
    })
  }

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

      {/* API Key */}
      <section className="space-y-4 rounded-lg border p-5">
        <div className="flex items-center gap-2">
          <Key className="h-4 w-4 text-muted-foreground" />
          <h2 className="text-sm font-semibold">API Key</h2>
        </div>
        <p className="text-xs text-muted-foreground">
          Generate an API key for programmatic access. The full key is shown only once after
          generation.
        </p>
        {keyStatus === 'unknown' && keyLoading ? (
          <div className="flex items-center gap-2 py-2">
            <Spinner size="sm" />
            <span className="text-xs text-muted-foreground">Loading key status...</span>
          </div>
        ) : keyStatus === 'none' ? (
          <button
            type="button"
            onClick={() => void handleGenerateKey()}
            disabled={keyLoading}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {keyLoading ? (
              <Spinner size="sm" className="text-current" />
            ) : (
              <Key className="h-3.5 w-3.5" />
            )}
            Generate Key
          </button>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-[10px] font-medium text-emerald-700 dark:bg-emerald-900 dark:text-emerald-400">
                Active
              </span>
              {revealedKey && showKey ? (
                <div className="flex items-center gap-1.5">
                  <code className="rounded border bg-muted px-2 py-1 font-mono text-xs">
                    {revealedKey}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopyKey}
                    aria-label="Copy API key"
                    title="Copy to clipboard"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    <Copy className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setShowKey(false)}
                    aria-label="Hide API key"
                    title="Hide key"
                    className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                  >
                    <EyeOff className="h-3.5 w-3.5" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-1.5">
                  <code className="rounded border bg-muted px-2 py-1 font-mono text-xs text-muted-foreground">
                    {maskedKey || 'bb-****...****'}
                  </code>
                  {revealedKey && (
                    <button
                      type="button"
                      onClick={() => setShowKey(true)}
                      aria-label="Show API key"
                      title="Show key"
                      className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    >
                      <Eye className="h-3.5 w-3.5" />
                    </button>
                  )}
                </div>
              )}
            </div>
            {revealedKey && (
              <p className="text-[11px] text-amber-600 dark:text-amber-400">
                Save this key now. It will not be shown again after you leave or refresh.
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setRotateOpen(true)}
                disabled={keyLoading}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-accent disabled:cursor-not-allowed disabled:opacity-50"
              >
                <RotateCw className="h-3 w-3" />
                Rotate
              </button>
              <button
                type="button"
                onClick={() => setRevokeOpen(true)}
                disabled={keyLoading}
                className="inline-flex items-center gap-1.5 rounded-md border border-red-200 px-3 py-1.5 text-xs font-medium text-red-600 transition-colors hover:bg-red-50 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
              >
                <Trash2 className="h-3 w-3" />
                Revoke
              </button>
            </div>
          </div>
        )}
      </section>

      <ConfirmDialog
        open={rotateOpen}
        onOpenChange={setRotateOpen}
        title="Rotate API Key"
        description="This will invalidate your current API key and generate a new one. Any integrations using the old key will stop working."
        confirmLabel="Rotate Key"
        onConfirm={handleRotateKey}
        loading={keyLoading}
      />

      <ConfirmDialog
        open={revokeOpen}
        onOpenChange={setRevokeOpen}
        title="Revoke API Key"
        description="This will permanently delete your API key. You will need to generate a new one for programmatic access."
        confirmLabel="Revoke Key"
        confirmVariant="destructive"
        onConfirm={handleRevokeKey}
        loading={keyLoading}
      />

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
