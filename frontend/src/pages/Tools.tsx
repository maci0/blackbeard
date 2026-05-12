import { useEffect, useState, useMemo } from 'react'
import { Wrench, Search, AlertTriangle, RefreshCw, Code2, Box, Shield } from 'lucide-react'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Type badge                                                          */
/* ------------------------------------------------------------------ */

const TYPE_CLASSES: Record<string, string> = {
  python: 'bg-blue-100 text-blue-700 border-blue-200',
  wasm: 'bg-violet-100 text-violet-700 border-violet-200',
  builtin: 'bg-emerald-100 text-emerald-700 border-emerald-200',
}

const TYPE_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  python: Code2,
  wasm: Box,
  builtin: Shield,
}

const TYPE_DISPLAY: Record<string, string> = {
  python: 'Python',
  wasm: 'WebAssembly',
  builtin: 'Built-in',
}

function TypeBadge({ type }: { type: string }) {
  const Icon = TYPE_ICONS[type] ?? Wrench
  const label = TYPE_DISPLAY[type] ?? type
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border',
        TYPE_CLASSES[type] ?? 'bg-gray-100 text-gray-600 border-gray-200',
      )}
    >
      <Icon className="h-3 w-3" />
      {label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Sandbox tier badge                                                  */
/* ------------------------------------------------------------------ */

const SANDBOX_CLASSES: Record<string, string> = {
  none: 'bg-gray-100 text-gray-700',
  wasm: 'bg-purple-100 text-purple-700',
}

const SANDBOX_DISPLAY: Record<string, string> = {
  none: 'No sandbox',
  wasm: 'WebAssembly (WASM)',
}

function SandboxLabel({ tier }: { tier: string }) {
  const label = SANDBOX_DISPLAY[tier] ?? tier
  return (
    <span className={cn('text-xs font-medium', SANDBOX_CLASSES[tier] ?? 'text-muted-foreground')}>
      {label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Tool card                                                           */
/* ------------------------------------------------------------------ */

function ToolCard({ resource }: { resource: Resource }) {
  const spec = resource.spec as {
    type?: string
    class_path?: string
    description?: string
    sandbox?: string
    entrypoint?: string
  }

  return (
    <div className="border rounded-lg bg-card shadow-sm hover:shadow-md transition-shadow flex flex-col overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b bg-muted/20">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="p-1.5 rounded-md bg-emerald-100 border border-emerald-200 shrink-0">
              <Wrench className="h-4 w-4 text-emerald-600" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm truncate">{resource.metadata.name}</p>
              <p className="text-xs text-muted-foreground">
                {resource.metadata.namespace || 'default'}
              </p>
            </div>
          </div>
          {spec.type && <TypeBadge type={spec.type} />}
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 flex-1 flex flex-col gap-2.5">
        {spec.description && (
          <p className="text-sm text-muted-foreground line-clamp-3 leading-relaxed">
            {spec.description}
          </p>
        )}

        {spec.class_path && (
          <div>
            <p className="text-xs text-muted-foreground/70 mb-0.5">Class path</p>
            <p className="text-xs font-mono truncate text-foreground/80 bg-muted/50 rounded px-1.5 py-0.5">
              {spec.class_path}
            </p>
          </div>
        )}

        {spec.entrypoint && (
          <div>
            <p className="text-xs text-muted-foreground/70 mb-0.5">Entrypoint</p>
            <p className="text-xs font-mono truncate text-foreground/80 bg-muted/50 rounded px-1.5 py-0.5">
              {spec.entrypoint}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2.5 border-t bg-muted/10 flex items-center justify-between">
        {spec.sandbox ? (
          <SandboxLabel tier={spec.sandbox} />
        ) : (
          <span className="text-xs text-muted-foreground/50">—</span>
        )}
        <span className="text-xs text-muted-foreground">v{resource.version}</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Tools() {
  const { resources, loading, error, fetchResources } = useResourceStore()
  const [search, setSearch] = useState('')

  const tools = resources['tools'] ?? []

  useEffect(() => {
    document.title = 'Tools | Blackbeard'
    return () => { document.title = 'Blackbeard' }
  }, [])

  useEffect(() => {
    fetchResources('tools')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const filtered = useMemo(() => {
    if (!search.trim()) return tools
    const q = search.toLowerCase()
    return tools.filter(
      (t) =>
        t.metadata.name.toLowerCase().includes(q) ||
        ((t.spec as { description?: string }).description ?? '').toLowerCase().includes(q) ||
        ((t.spec as { type?: string }).type ?? '').toLowerCase().includes(q),
    )
  }, [tools, search])

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Tools</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Tool registry — python, wasm, and builtin tools
            </p>
          </div>
          <button
            onClick={() => fetchResources('tools')}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md bg-background hover:bg-accent transition-colors"
          >
            <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin motion-reduce:animate-none')} />
            Refresh
          </button>
        </div>

        {/* Error */}
        {error && (
          <div role="alert" className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Search */}
        {tools.length > 0 && (
          <div className="relative max-w-sm mb-5">
            <label htmlFor="tools-search" className="sr-only">Search tools</label>
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <input
              id="tools-search"
              type="text"
              placeholder="Search tools…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
        )}

        {/* Content */}
        {loading && tools.length === 0 ? (
          <div className="flex items-center justify-center py-24">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner size="sm" className="text-muted-foreground" />
              <span className="text-sm">Loading tools…</span>
            </div>
          </div>
        ) : filtered.length === 0 ? (
          <div className="border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-24 px-6 text-center">
            <div className="p-4 rounded-full bg-muted mb-4">
              <Wrench className="h-8 w-8 text-muted-foreground/50" />
            </div>
            <p className="font-medium text-muted-foreground mb-1">
              {search ? 'No tools match your search' : 'No tools registered'}
            </p>
            <p className="text-sm text-muted-foreground/70">
              {search
                ? 'Try a different search term'
                : 'Define Tool resources and apply them via the CLI'}
            </p>
            {search && (
              <button
                onClick={() => setSearch('')}
                className="mt-3 text-sm text-primary hover:underline underline-offset-2"
              >
                Clear search
              </button>
            )}
          </div>
        ) : (
          <>
            {search && (
              <p className="text-sm text-muted-foreground mb-4">
                {filtered.length} of {tools.length} tools
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
              {filtered.map((resource) => (
                <ToolCard key={resource.id} resource={resource} />
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
