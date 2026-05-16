import { useEffect, useState, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useDocumentTitle } from '@/lib/hooks'
import { Wrench, Search, RefreshCw, Code2, Box, Shield, X } from 'lucide-react'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Type badge                                                          */
/* ------------------------------------------------------------------ */

const TYPE_CLASSES: Record<string, string> = {
  python:
    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  wasm: 'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900 dark:text-violet-300 dark:border-violet-800',
  builtin:
    'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
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
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        TYPE_CLASSES[type] ??
          'border-gray-200 bg-gray-100 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300',
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
  none: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
  wasm: 'bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-300',
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
    <Link
      to={`/resources/tools/${resource.metadata.name}`}
      aria-label={`Tool: ${resource.metadata.name}${spec.type ? ` (${TYPE_DISPLAY[spec.type] ?? spec.type})` : ''}`}
      className="flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
    >
      {/* Header */}
      <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 rounded-md border border-emerald-200 bg-emerald-100 p-1.5">
              <Wrench className="h-4 w-4 text-emerald-600" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold" title={resource.metadata.name}>
                {resource.metadata.name}
              </p>
              {resource.metadata.namespace && resource.metadata.namespace !== 'default' && (
                <p className="text-xs text-muted-foreground">{resource.metadata.namespace}</p>
              )}
            </div>
          </div>
          {spec.type && <TypeBadge type={spec.type} />}
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2.5 px-4 py-3">
        {spec.description && (
          <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
            {spec.description}
          </p>
        )}

        {spec.class_path && (
          <div>
            <p className="mb-0.5 text-xs text-muted-foreground/70">Class path</p>
            <p className="truncate rounded bg-muted/50 px-1.5 py-0.5 font-mono text-xs text-foreground/80">
              {spec.class_path}
            </p>
          </div>
        )}

        {spec.entrypoint && (
          <div>
            <p className="mb-0.5 text-xs text-muted-foreground/70">Entrypoint</p>
            <p className="truncate rounded bg-muted/50 px-1.5 py-0.5 font-mono text-xs text-foreground/80">
              {spec.entrypoint}
            </p>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t bg-muted/10 px-4 py-2.5">
        {spec.sandbox ? (
          <SandboxLabel tier={spec.sandbox} />
        ) : (
          <span className="text-xs text-muted-foreground/50">--</span>
        )}
        <span className="text-xs text-muted-foreground">v{resource.version}</span>
      </div>
    </Link>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Tools() {
  const { resources, loading, error, fetchResources } = useResourceStore()
  const [search, setSearch] = useState('')

  const tools = useMemo(() => resources['tools'] ?? [], [resources])

  useDocumentTitle('Tools')

  useEffect(() => {
    void fetchResources('tools')
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
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Tools"
            description="Tool library and registry"
            actions={
              <>
                <button
                  onClick={() => void fetchResources('tools')}
                  aria-label="Refresh tools"
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <RefreshCw
                    className={cn(
                      'h-3.5 w-3.5',
                      loading && 'animate-spin motion-reduce:animate-none',
                    )}
                  />
                  Refresh
                </button>
                <Link
                  to="/studio"
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Create in Studio
                </Link>
              </>
            }
          />
        </div>

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchResources('tools')}
            ariaLabel="Retry loading tools"
            className="mb-4"
          />
        )}

        {/* Search */}
        {tools.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <label htmlFor="tools-search" className="sr-only">
                Search tools
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                id="tools-search"
                type="search"
                placeholder="Search tools…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            {search && (
              <>
                <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
                  {filtered.length} of {tools.length} tools
                </span>
                <button
                  onClick={() => setSearch('')}
                  aria-label="Clear search"
                  className="inline-flex items-center gap-1 rounded text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                  Clear search
                </button>
              </>
            )}
          </div>
        )}

        {/* Content */}
        {loading && tools.length === 0 ? (
          <TableSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Wrench />}
            title={search ? 'No tools match your search' : 'No tools found'}
            description={search ? 'Try a different search term' : 'Create tools in the Studio'}
            action={!search ? { label: 'Go to Studio', href: '/studio' } : undefined}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((resource) => (
              <ToolCard key={resource.id} resource={resource} />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
