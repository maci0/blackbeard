import { useEffect, useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Database, Search, ChevronRight, RefreshCw, AlertTriangle, X } from 'lucide-react'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { KindBadge } from '@/components/ui/KindBadge'
import { Spinner } from '@/components/ui/Spinner'
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
  const { resources, loading, error, fetchAllResources } = useResourceStore()
  const [kindFilter, setKindFilter] = useState('')
  const [search, setSearch] = useState('')

  useDocumentTitle('Resources')

  useEffect(() => {
    fetchAllResources()
    // eslint-disable-next-line react-hooks/exhaustive-deps -- run once on mount; fetchAllResources is stable
  }, [])

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
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Resources</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Agents, tasks, crews, tools, and policies
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchAllResources()}
              aria-label="Refresh resources"
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md bg-background hover:bg-accent transition-colors"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin motion-reduce:animate-none')} />
              Refresh
            </button>
            <button
              onClick={() => navigate('/studio')}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
            >
              Create in Studio
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div role="alert" className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center justify-between">
            <span className="flex items-center gap-2">
              <AlertTriangle className="h-4 w-4 shrink-0" />
              {error}
            </span>
            <button onClick={() => fetchAllResources()} className="text-xs underline underline-offset-2" aria-label="Retry loading resources">
              Retry
            </button>
          </div>
        )}

        {/* Filters */}
        <div className="flex items-center gap-3 mb-4 flex-wrap">
          <div className="relative flex-1 min-w-[200px] max-w-sm">
            <label htmlFor="resources-search" className="sr-only">Search resources by name</label>
            <Search aria-hidden="true" className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground pointer-events-none" />
            <input
              id="resources-search"
              type="text"
              placeholder="Search by name…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full pl-9 pr-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <label htmlFor="resources-kind-filter" className="sr-only">Filter by kind</label>
          <select
            id="resources-kind-filter"
            value={kindFilter}
            onChange={(e) => setKindFilter(e.target.value)}
            className="px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
          >
            {FILTER_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </select>
          <span className="text-sm text-muted-foreground">
            {filtered.length} {filtered.length === 1 ? 'result' : 'results'}
          </span>
          {(search || kindFilter) && (
            <button
              onClick={() => { setSearch(''); setKindFilter('') }}
              aria-label="Clear all filters"
              className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              <X className="h-3.5 w-3.5" />
              Clear filters
            </button>
          )}
        </div>

        {/* Table */}
        <div className="border rounded-lg overflow-hidden bg-card shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-sm" aria-label="Resources">
              <thead>
                <tr className="border-b bg-muted/40">
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    Kind
                  </th>
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    Name
                  </th>
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    Namespace
                  </th>
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    Version
                  </th>
                  <th scope="col" className="text-left px-4 py-3 font-medium text-muted-foreground text-xs uppercase tracking-wider">
                    Updated
                  </th>
                  <th scope="col" className="w-8 px-4 py-3">
                    <span className="sr-only">Details</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {loading && filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-16 text-center text-muted-foreground">
                      <div className="flex items-center justify-center gap-2">
                        <Spinner size="sm" className="text-muted-foreground" />
                        <span className="text-sm">Loading resources…</span>
                      </div>
                    </td>
                  </tr>
                ) : filtered.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="px-4 py-16 text-center">
                      <Database aria-hidden="true" className="h-8 w-8 text-muted-foreground/30 mx-auto mb-3" />
                      <p className="font-medium text-muted-foreground">No resources found</p>
                      {search || kindFilter ? (
                        <p className="text-sm text-muted-foreground/70 mt-1">
                          Try adjusting your filters
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground/70 mt-1">
                          Create resources in the Studio
                        </p>
                      )}
                    </td>
                  </tr>
                ) : (
                  filtered.map((resource) => (
                    <tr
                      key={`${resource.kindPlural}/${resource.metadata.name}`}
                      onClick={() =>
                        navigate(`/resources/${resource.kindPlural}/${resource.metadata.name}`)
                      }
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          navigate(`/resources/${resource.kindPlural}/${resource.metadata.name}`)
                        }
                      }}
                      tabIndex={0}
                      role="row"
                      aria-label={`${resource.kind}: ${resource.metadata.name} — press Enter to view details`}
                      className="border-b last:border-0 hover:bg-muted/40 cursor-pointer transition-colors group focus-visible:outline-none focus-visible:bg-muted/60 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                    >
                      <td className="px-4 py-3">
                        <KindBadge kind={resource.kind} />
                      </td>
                      <td className="px-4 py-3 font-medium">{resource.metadata.name}</td>
                       <td className="px-4 py-3 text-muted-foreground">
                         {(!resource.metadata.namespace || resource.metadata.namespace === 'default')
                           ? <span className="text-muted-foreground/40" aria-label="default namespace">—</span>
                           : resource.metadata.namespace}
                       </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        v{resource.version}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(resource.updated_at)}
                      </td>
                      <td className="px-4 py-3">
                        <ChevronRight aria-hidden="true" className="h-4 w-4 text-muted-foreground/40 group-hover:text-muted-foreground transition-colors" />
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}
