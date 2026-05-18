import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Database, Search, ChevronRight, RefreshCw, X } from 'lucide-react'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { KindBadge } from '@/components/ui/KindBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn } from '@/lib/utils'
import { formatDate } from '@/lib/formatters'
import { KIND_TO_PLURAL } from '@/lib/kinds'
import { useDocumentTitle } from '@/lib/hooks'

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const FILTER_OPTIONS = [
  { label: 'All kinds', value: '' },
  ...Object.entries(KIND_TO_PLURAL).map(([kind, plural]) => ({ label: kind, value: plural })),
]

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Resources() {
  const navigate = useNavigate()
  const resources = useResourceStore((s) => s.resources)
  const loading = useResourceStore((s) => s.loading)
  const error = useResourceStore((s) => s.error)
  const fetchAllResources = useResourceStore((s) => s.fetchAllResources)
  const [kindFilter, setKindFilter] = useState('')
  const [search, setSearch] = useState('')

  useDocumentTitle('Resources')

  useEffect(() => {
    void fetchAllResources()
  }, [fetchAllResources])

  // Flatten all resources from the store
  const allResources = useMemo(() => {
    const result: Array<Resource & { kindPlural: string }> = []
    for (const [kindPlural, items] of Object.entries(resources)) {
      for (const item of items) {
        result.push({ ...item, kindPlural })
      }
    }
    return result
  }, [resources])

  const showNamespace = useMemo(
    () => allResources.some((r) => r.metadata.namespace && r.metadata.namespace !== 'default'),
    [allResources],
  )

  const filtered = useMemo(() => {
    return allResources.filter((r) => {
      if (kindFilter && r.kindPlural !== kindFilter) return false
      if (search) {
        const q = search.toLowerCase()
        if (!r.metadata.name.toLowerCase().includes(q) && !r.kind.toLowerCase().includes(q))
          return false
      }
      return true
    })
  }, [allResources, kindFilter, search])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Resources"
            description="Agents, tasks, crews, tools, and policies"
            actions={
              <>
                <button
                  onClick={() => void fetchAllResources()}
                  aria-label="Refresh resources"
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
                <button
                  onClick={() => void navigate('/studio')}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Create in Studio
                </button>
              </>
            }
          />
        </div>

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchAllResources()}
            ariaLabel="Retry loading resources"
            className="mb-4"
          />
        )}

        {/* Filters */}
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <div className="relative min-w-[200px] max-w-sm flex-1">
            <label htmlFor="resources-search" className="sr-only">
              Search resources by name
            </label>
            <Search
              aria-hidden="true"
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
            />
            <input
              id="resources-search"
              type="search"
              placeholder="Search by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              autoComplete="off"
              className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <label htmlFor="resources-kind-filter" className="sr-only">
            Filter by kind
          </label>
          <select
            id="resources-kind-filter"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {filtered.length} {filtered.length === 1 ? 'result' : 'results'}
          </span>
          {(search || kindFilter) && (
            <button
              onClick={() => {
                setSearch('')
                setKindFilter('')
              }}
              aria-label="Clear all filters"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          )}
        </div>

        {/* Table */}
        {loading && filtered.length === 0 ? (
          <TableSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Database />}
            title="No resources found"
            description={
              search || kindFilter ? 'Try adjusting your filters' : 'Create resources in the Studio'
            }
            action={
              !(search || kindFilter) ? { label: 'Go to Studio', href: '/studio' } : undefined
            }
          />
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-sm" aria-label="Resources">
                <thead>
                  <tr className="border-b bg-muted/60">
                    {(
                      [
                        'Kind',
                        'Name',
                        ...(showNamespace ? ['Namespace'] : []),
                        'Version',
                        'Updated',
                      ] as const
                    ).map((h) => (
                      <th
                        key={h}
                        scope="col"
                        className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                    <th scope="col" className="w-8 px-4 py-3">
                      <span className="sr-only">Details</span>
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border/50">
                  {filtered.map((resource) => (
                    <tr
                      key={`${resource.kindPlural}/${resource.metadata.name}`}
                      onClick={() =>
                        void navigate(`/resources/${resource.kindPlural}/${resource.metadata.name}`)
                      }
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          void navigate(
                            `/resources/${resource.kindPlural}/${resource.metadata.name}`,
                          )
                        }
                      }}
                      tabIndex={0}
                      role="row"
                      aria-label={`${resource.kind}: ${resource.metadata.name} — press Enter to view details`}
                      className="group cursor-pointer transition-colors duration-150 hover:bg-muted/40 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    >
                      <td className="px-4 py-3">
                        <KindBadge kind={resource.kind} />
                      </td>
                      <td className="px-4 py-3 font-medium">{resource.metadata.name}</td>
                      {showNamespace && (
                        <td className="px-4 py-3 text-muted-foreground">
                          {!resource.metadata.namespace ||
                          resource.metadata.namespace === 'default' ? (
                            <>
                              <span className="text-muted-foreground/40" aria-hidden="true">
                                —
                              </span>
                              <span className="sr-only">default namespace</span>
                            </>
                          ) : (
                            resource.metadata.namespace
                          )}
                        </td>
                      )}
                      <td className="px-4 py-3 text-muted-foreground">v{resource.version}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(resource.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <ChevronRight
                          aria-hidden="true"
                          className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
