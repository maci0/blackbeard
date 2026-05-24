import { useEffect, useState, useMemo, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Database,
  Search,
  ChevronRight,
  RefreshCw,
  X,
  Plus,
  AlertCircle,
  Loader2,
  Upload,
} from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { useShallow } from 'zustand/react/shallow'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { KindBadge } from '@/components/ui/KindBadge'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { cn, getErrorMessage } from '@/lib/utils'
import { formatDate } from '@/lib/formatters'
import { KIND_TO_PLURAL, API_VERSION } from '@/lib/kinds'
import { useDocumentTitle } from '@/hooks'
import { useToastStore } from '@/stores/toastStore'
import { parseYaml } from '@/lib/yaml'
import { Pagination } from '@/components/ui/Pagination'

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const FILTER_OPTIONS = [
  { label: 'All kinds', value: '' },
  ...Object.entries(KIND_TO_PLURAL).map(([kind, plural]) => ({ label: kind, value: plural })),
]

const KIND_ENTRIES = Object.entries(KIND_TO_PLURAL)

const PAGE_SIZE = 25

const NAME_RE = /^[a-z0-9][a-z0-9-]*$/

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Resources() {
  const navigate = useNavigate()
  const { resources, loading, error, fetchAllResources, createResource } = useResourceStore(
    useShallow((s) => ({
      resources: s.resources,
      loading: s.loading,
      error: s.error,
      fetchAllResources: s.fetchAllResources,
      createResource: s.createResource,
    })),
  )
  const toast = useToastStore()
  const [kindFilter, setKindFilter] = useState('')
  const [search, setSearch] = useState('')
  const [page, setPage] = useState(1)
  const searchRef = useRef<HTMLInputElement>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [newKind, setNewKind] = useState(KIND_ENTRIES[0]![0])
  const [newName, setNewName] = useState('')
  const [newNamespace, setNewNamespace] = useState('default')
  const [newSpec, setNewSpec] = useState('{}')
  const [specError, setSpecError] = useState('')
  const [nameError, setNameError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  async function handleYamlImport(file: File) {
    setImporting(true)
    try {
      const text = await file.text()
      const docs = text
        .split(/\n---(?:\n|$)/)
        .map((d) => d.trim())
        .filter(Boolean)
      let imported = 0
      for (const doc of docs) {
        const parsed = parseYaml(doc)
        const kind = typeof parsed.kind === 'string' ? parsed.kind : ''
        const metadata = parsed.metadata as
          | { name?: string; namespace?: string; labels?: Record<string, string> }
          | undefined
        const name = metadata?.name ?? ''
        const spec = (parsed.spec ?? {}) as Record<string, unknown>
        if (!kind || !name) {
          toast.error(`Skipped document: missing kind or metadata.name`)
          continue
        }
        const apiVersion = typeof parsed.apiVersion === 'string' ? parsed.apiVersion : API_VERSION
        try {
          await createResource({
            apiVersion,
            kind,
            metadata: {
              name,
              namespace: metadata?.namespace || 'default',
              labels: metadata?.labels,
            },
            spec,
          })
          toast.success(`Imported ${kind} "${name}"`)
          imported++
        } catch (err) {
          toast.error(getErrorMessage(err, `Failed to import ${kind} "${name}"`))
        }
      }
      if (imported > 0) {
        void fetchAllResources()
      }
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to read YAML file'))
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  function resetDialog() {
    setNewKind(KIND_ENTRIES[0]![0])
    setNewName('')
    setNewNamespace('default')
    setNewSpec('{}')
    setSpecError('')
    setNameError('')
  }

  function validateName(v: string): string {
    if (!v) return 'Name is required'
    if (!NAME_RE.test(v))
      return 'Lowercase alphanumeric and hyphens only, must start with letter or digit'
    return ''
  }

  function validateSpec(v: string): string {
    if (!v.trim()) return 'Spec is required'
    try {
      JSON.parse(v)
      return ''
    } catch {
      return 'Invalid JSON'
    }
  }

  async function handleCreateResource() {
    const ne = validateName(newName)
    const se = validateSpec(newSpec)
    setNameError(ne)
    setSpecError(se)
    if (ne || se) return

    setSubmitting(true)
    try {
      await createResource({
        apiVersion: API_VERSION,
        kind: newKind,
        metadata: { name: newName, namespace: newNamespace || 'default' },
        spec: JSON.parse(newSpec) as Record<string, unknown>,
      })
      toast.success(`Created ${newKind} "${newName}"`)
      setDialogOpen(false)
      resetDialog()
      void fetchAllResources()
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to create resource'))
    } finally {
      setSubmitting(false)
    }
  }

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

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return filtered.slice(start, start + PAGE_SIZE)
  }, [filtered, page])

  const handleKindFilterChange = useCallback((value: string) => {
    setKindFilter(value)
    setPage(1)
  }, [])

  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    setPage(1)
  }, [])

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
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".yaml,.yml"
                  className="hidden"
                  aria-hidden="true"
                  tabIndex={-1}
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (file) void handleYamlImport(file)
                  }}
                />
                <button
                  type="button"
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
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={importing}
                  aria-busy={importing}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {importing ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                  ) : (
                    <Upload className="h-3.5 w-3.5" />
                  )}
                  Import YAML
                </button>
                <button
                  type="button"
                  onClick={() => {
                    resetDialog()
                    setDialogOpen(true)
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-3.5 w-3.5" />
                  New Resource
                </button>
                <button
                  type="button"
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
              ref={searchRef}
              id="resources-search"
              type="search"
              placeholder="Search by name…"
              value={search}
              onChange={(e) => handleSearchChange(e.target.value)}
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
            onChange={(e) => handleKindFilterChange(e.target.value)}
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
              type="button"
              onClick={() => {
                setSearch('')
                setKindFilter('')
                setPage(1)
                searchRef.current?.focus()
              }}
              aria-label="Clear all filters"
              className="inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
          <>
            <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
              <div className="max-h-[calc(100vh-16rem)] overflow-auto">
                <table className="w-full min-w-[640px] text-sm" aria-label="Resources">
                  <thead className="sticky top-0 z-10">
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
                  <tbody className="divide-y divide-border">
                    {paginated.map((resource) => (
                      <tr
                        key={`${resource.kindPlural}/${resource.metadata.name}`}
                        onClick={() =>
                          void navigate(
                            `/resources/${resource.kindPlural}/${resource.metadata.name}`,
                          )
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
                        className="group cursor-pointer transition-colors duration-150 hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
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
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        )}
      </div>

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div>
                <Dialog.Title className="text-lg font-semibold">New Resource</Dialog.Title>
                <Dialog.Description className="mt-0.5 text-sm text-muted-foreground">
                  Create a resource by specifying its kind, name, and spec.
                </Dialog.Description>
              </div>
              <Dialog.Close
                className="flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Close"
                title="Close"
              >
                <X className="h-4 w-4" />
              </Dialog.Close>
            </div>

            <form
              onSubmit={(e) => {
                e.preventDefault()
                void handleCreateResource()
              }}
              noValidate
              className="space-y-4 p-5"
            >
              <fieldset disabled={submitting} className="space-y-4">
                <div>
                  <label
                    htmlFor="new-resource-kind"
                    className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    Kind
                  </label>
                  <select
                    id="new-resource-kind"
                    value={newKind}
                    onChange={(e) => setNewKind(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    {KIND_ENTRIES.map(([kind]) => (
                      <option key={kind} value={kind}>
                        {kind}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="new-resource-name"
                    className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    Name
                  </label>
                  <input
                    id="new-resource-name"
                    type="text"
                    value={newName}
                    onChange={(e) => {
                      setNewName(e.target.value)
                      if (nameError) setNameError(validateName(e.target.value))
                    }}
                    onBlur={() => setNameError(validateName(newName))}
                    aria-invalid={nameError ? true : undefined}
                    aria-describedby={nameError ? 'new-resource-name-error' : undefined}
                    placeholder="my-resource"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                  {nameError && (
                    <p
                      id="new-resource-name-error"
                      role="alert"
                      className="mt-1 flex items-center gap-1 text-xs text-destructive"
                    >
                      <AlertCircle className="h-3 w-3" />
                      {nameError}
                    </p>
                  )}
                </div>

                <div>
                  <label
                    htmlFor="new-resource-namespace"
                    className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    Namespace
                  </label>
                  <input
                    id="new-resource-namespace"
                    type="text"
                    value={newNamespace}
                    onChange={(e) => setNewNamespace(e.target.value)}
                    placeholder="default"
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                </div>

                <div>
                  <label
                    htmlFor="new-resource-spec"
                    className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    Spec (JSON)
                  </label>
                  <textarea
                    id="new-resource-spec"
                    value={newSpec}
                    onChange={(e) => {
                      setNewSpec(e.target.value)
                      if (specError) setSpecError(validateSpec(e.target.value))
                    }}
                    onBlur={() => setSpecError(validateSpec(newSpec))}
                    aria-invalid={specError ? true : undefined}
                    aria-describedby={specError ? 'new-resource-spec-error' : undefined}
                    placeholder='{ "role": "researcher" }'
                    spellCheck={false}
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    className="h-32 w-full resize-none rounded-md border bg-background px-3 py-2.5 font-mono text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  />
                  {specError && (
                    <p
                      id="new-resource-spec-error"
                      role="alert"
                      className="mt-1 flex items-center gap-1 text-xs text-destructive"
                    >
                      <AlertCircle className="h-3 w-3" />
                      {specError}
                    </p>
                  )}
                </div>
              </fieldset>

              <div className="flex justify-end gap-3">
                <Dialog.Close asChild>
                  <button
                    type="button"
                    className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    Cancel
                  </button>
                </Dialog.Close>
                <button
                  type="submit"
                  disabled={submitting}
                  aria-busy={submitting}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                  )}
                  Create
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
