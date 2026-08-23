import { useEffect, useState, useMemo, useRef, useCallback, useDeferredValue } from 'react'
import { useNavigate, Link } from 'react-router-dom'
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
  Trash2,
  ClipboardPaste,
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
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ApiError } from '@/api/client'
import { caseFold, cn, getErrorMessage } from '@/lib/utils'
import { SmartTime } from '@/components/ui/SmartTime'
import { KIND_TO_PLURAL, API_VERSION, NAME_RE } from '@/lib/kinds'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useToastStore } from '@/stores/toastStore'
import { parseYamlDocs } from '@/lib/yaml'
import { Pagination } from '@/components/ui/Pagination'
import { ViewToggle } from '@/components/ui/ViewToggle'
import { useViewPrefsStore } from '@/stores/viewPrefsStore'

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const FILTER_OPTIONS = [
  { label: 'All kinds', value: '' },
  ...Object.entries(KIND_TO_PLURAL).map(([kind, plural]) => ({ label: kind, value: plural })),
]

const KIND_ENTRIES = Object.entries(KIND_TO_PLURAL)

const PAGE_SIZE = 25

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Resources() {
  const navigate = useNavigate()
  const { resources, loading, error, fetchAllResources, createResource, deleteResource } =
    useResourceStore(
      useShallow((s) => ({
        resources: s.resources,
        loading: s.loading,
        error: s.error,
        fetchAllResources: s.fetchAllResources,
        createResource: s.createResource,
        deleteResource: s.deleteResource,
      })),
    )
  const toast = useToastStore()
  const [kindFilter, setKindFilter] = useState('')
  const [search, setSearch] = useState('')
  const deferredSearch = useDeferredValue(search)
  const [page, setPage] = useState(1)
  const searchRef = useRef<HTMLInputElement>(null)

  const [dialogOpen, setDialogOpen] = useState(false)
  const [newKind, setNewKind] = useState(KIND_ENTRIES[0]![0])
  const [newName, setNewName] = useState('')
  const [newProject, setNewProject] = useState('default')
  const [newSpec, setNewSpec] = useState('{}')
  const [specError, setSpecError] = useState('')
  const [nameError, setNameError] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [bulkDeleteOpen, setBulkDeleteOpen] = useState(false)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteYaml, setPasteYaml] = useState('')
  const [pasteImporting, setPasteImporting] = useState(false)
  const { getView, setView } = useViewPrefsStore()
  const viewMode = getView('resources')

  useEffect(() => {
    setSelectedIds(new Set())
  }, [kindFilter, search])

  const toggleSelected = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }, [])

  async function importYamlDocs(text: string): Promise<number> {
    const docs = parseYamlDocs(text)
    let imported = 0
    for (const parsed of docs) {
      const kind = typeof parsed.kind === 'string' ? parsed.kind : ''
      const metadata = parsed.metadata as
        | { name?: string; project?: string; labels?: Record<string, string> }
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
            project: metadata?.project || 'default',
            labels: metadata?.labels,
          },
          spec,
        })
        imported++
      } catch (err) {
        if (err instanceof ApiError && Array.isArray(err.detail)) {
          const msgs = (err.detail as Array<{ field?: string; message?: string }>)
            .map((e) => e.message ?? '')
            .filter(Boolean)
            .join('; ')
          toast.error(`${kind}/${name}: ${msgs || 'Validation failed'}`)
        } else {
          toast.error(getErrorMessage(err, `Failed to import ${kind} "${name}"`))
        }
      }
    }
    if (imported > 0) void fetchAllResources()
    return imported
  }

  async function handleYamlImport(file: File) {
    setImporting(true)
    try {
      const text = await file.text()
      const count = await importYamlDocs(text)
      if (count > 0) toast.success(`Imported ${count} resource${count === 1 ? '' : 's'}`)
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to read YAML file'))
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  async function handlePasteImport() {
    const text = pasteYaml.trim()
    if (!text) return
    setPasteImporting(true)
    try {
      const count = await importYamlDocs(text)
      if (count > 0) toast.success(`Imported ${count} resource${count === 1 ? '' : 's'}`)
      setPasteOpen(false)
      setPasteYaml('')
    } catch (err) {
      toast.error(getErrorMessage(err, 'Failed to parse YAML'))
    } finally {
      setPasteImporting(false)
    }
  }

  function resetDialog() {
    setNewKind(KIND_ENTRIES[0]![0])
    setNewName('')
    setNewProject('default')
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
        metadata: { name: newName, project: newProject || 'default' },
        spec: JSON.parse(newSpec) as Record<string, unknown>,
      })
      toast.success(`Created ${newKind} "${newName}"`)
      setDialogOpen(false)
      resetDialog()
      void fetchAllResources()
    } catch (err) {
      if (err instanceof ApiError && Array.isArray(err.detail)) {
        const msgs = (err.detail as Array<{ field?: string; message?: string }>)
          .map((e) => `${e.field ?? ''}: ${e.message ?? ''}`.trim())
          .join('\n')
        setSpecError(msgs || 'Validation failed')
      } else {
        toast.error(getErrorMessage(err, 'Failed to create resource'))
      }
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

  const showProject = useMemo(
    () => allResources.some((r) => r.metadata.project && r.metadata.project !== 'default'),
    [allResources],
  )

  const filtered = useMemo(() => {
    return allResources.filter((r) => {
      if (kindFilter && r.kindPlural !== kindFilter) return false
      if (deferredSearch) {
        const q = caseFold(deferredSearch)
        if (!caseFold(r.metadata.name).includes(q) && !caseFold(r.kind).includes(q)) return false
      }
      return true
    })
  }, [allResources, kindFilter, deferredSearch])

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const paginated = useMemo(() => {
    const start = (page - 1) * PAGE_SIZE
    return filtered.slice(start, start + PAGE_SIZE)
  }, [filtered, page])

  const toggleAllVisible = useCallback(() => {
    setSelectedIds((prev) => {
      const visibleIds = paginated.map((r) => `${r.kindPlural}/${r.metadata.name}`)
      const allSelected = visibleIds.every((id) => prev.has(id))
      if (allSelected) {
        const next = new Set(prev)
        for (const id of visibleIds) next.delete(id)
        return next
      }
      return new Set([...prev, ...visibleIds])
    })
  }, [paginated])

  const handleBulkDelete = async () => {
    setBulkDeleting(true)
    let deleted = 0
    for (const id of selectedIds) {
      const [kindPlural, ...rest] = id.split('/')
      const name = rest.join('/')
      if (!kindPlural || !name) continue
      try {
        await deleteResource(kindPlural, name)
        deleted++
      } catch (err) {
        toast.error(getErrorMessage(err, `Failed to delete ${name}`))
      }
    }
    if (deleted > 0) {
      toast.success(`Deleted ${deleted} resource${deleted === 1 ? '' : 's'}`)
    }
    setSelectedIds(new Set())
    setBulkDeleteOpen(false)
    setBulkDeleting(false)
  }

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
                <ViewToggle mode={viewMode} onChange={(m) => setView('resources', m)} />
                <button
                  type="button"
                  onClick={() => void fetchAllResources()}
                  disabled={loading}
                  aria-label="Refresh resources"
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
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
                    setPasteYaml('')
                    setPasteOpen(true)
                  }}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <ClipboardPaste className="h-3.5 w-3.5" />
                  Paste YAML
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
                <Link
                  to="/studio"
                  className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
            onAction={() => void fetchAllResources()}
            ariaLabel="Retry loading resources"
            className="mb-4"
          />
        )}

        {selectedIds.size > 0 && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-primary/20 bg-primary/5 px-4 py-2.5">
            <span className="text-sm font-medium">{selectedIds.size} selected</span>
            <button
              type="button"
              onClick={() => setBulkDeleteOpen(true)}
              className="inline-flex items-center gap-1.5 rounded-md bg-destructive px-3 py-1.5 text-sm font-medium text-destructive-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Trash2 className="h-3.5 w-3.5" />
              Delete selected
            </button>
            <button
              type="button"
              onClick={() => setSelectedIds(new Set())}
              className="ml-auto text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Clear selection
            </button>
          </div>
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
        ) : viewMode === 'cards' ? (
          <>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {paginated.map((resource) => {
                const cardId = `${resource.kindPlural}/${resource.metadata.name}`
                const isSelected = selectedIds.has(cardId)
                return (
                  <div
                    key={cardId}
                    onClick={() =>
                      void navigate(`/resources/${resource.kindPlural}/${resource.metadata.name}`)
                    }
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        void navigate(`/resources/${resource.kindPlural}/${resource.metadata.name}`)
                      }
                    }}
                    tabIndex={0}
                    role="article"
                    aria-label={`${resource.kind}: ${resource.metadata.name}`}
                    className={cn(
                      'group relative flex cursor-pointer flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                      isSelected && 'ring-2 ring-primary',
                    )}
                  >
                    <div
                      className={cn(
                        'absolute left-2 top-2 z-10',
                        selectedIds.size > 0 ? 'visible' : 'invisible group-hover:visible',
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={isSelected}
                        onChange={(e) => {
                          e.stopPropagation()
                          toggleSelected(cardId)
                        }}
                        onClick={(e) => e.stopPropagation()}
                        aria-label={`Select ${resource.metadata.name}`}
                        className="h-4 w-4 rounded border-muted-foreground/40 bg-background accent-primary shadow-sm"
                      />
                    </div>
                    <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0 pl-5">
                          <p
                            className="truncate text-sm font-semibold"
                            title={resource.metadata.name}
                          >
                            {resource.metadata.name}
                          </p>
                          {showProject &&
                            resource.metadata.project &&
                            resource.metadata.project !== 'default' && (
                              <p className="text-xs text-muted-foreground">
                                {resource.metadata.project}
                              </p>
                            )}
                        </div>
                        <KindBadge kind={resource.kind} />
                      </div>
                    </div>
                    <div className="flex-1 px-4 py-3">
                      <div className="flex items-center justify-between text-xs text-muted-foreground">
                        <span>v{resource.version}</span>
                        <span>
                          <SmartTime date={resource.updated_at} />
                        </span>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        ) : (
          <>
            <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
              <div className="max-h-[calc(100vh-16rem)] overflow-auto">
                <table className="w-full min-w-[640px] text-sm" aria-label="Resources">
                  <thead className="sticky top-0 z-10">
                    <tr className="border-b bg-muted/60">
                      <th scope="col" className="w-10 px-3 py-3">
                        <input
                          type="checkbox"
                          checked={
                            paginated.length > 0 &&
                            paginated.every((r) =>
                              selectedIds.has(`${r.kindPlural}/${r.metadata.name}`),
                            )
                          }
                          onChange={toggleAllVisible}
                          aria-label="Select all visible resources"
                          className="h-4 w-4 rounded border-muted-foreground/40 accent-primary"
                        />
                      </th>
                      {(
                        [
                          'Kind',
                          'Name',
                          ...(showProject ? ['Project'] : []),
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
                    {paginated.map((resource) => {
                      const rowId = `${resource.kindPlural}/${resource.metadata.name}`
                      return (
                        <tr
                          key={rowId}
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
                          className={cn(
                            'group cursor-pointer border-l-2 border-l-transparent transition-all duration-150 hover:border-l-primary hover:bg-accent/50 focus-visible:border-l-primary focus-visible:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                            selectedIds.has(rowId) && 'bg-primary/5',
                          )}
                        >
                          <td className="px-3 py-3">
                            <input
                              type="checkbox"
                              checked={selectedIds.has(rowId)}
                              onChange={(e) => {
                                e.stopPropagation()
                                toggleSelected(rowId)
                              }}
                              onClick={(e) => e.stopPropagation()}
                              aria-label={`Select ${resource.metadata.name}`}
                              className="h-4 w-4 rounded border-muted-foreground/40 accent-primary"
                            />
                          </td>
                          <td className="px-4 py-3">
                            <KindBadge kind={resource.kind} />
                          </td>
                          <td className="px-4 py-3 font-medium">{resource.metadata.name}</td>
                          {showProject && (
                            <td className="px-4 py-3 text-muted-foreground">
                              {!resource.metadata.project ||
                              resource.metadata.project === 'default' ? (
                                <>
                                  <span className="text-muted-foreground/40" aria-hidden="true">
                                    —
                                  </span>
                                  <span className="sr-only">default project</span>
                                </>
                              ) : (
                                resource.metadata.project
                              )}
                            </td>
                          )}
                          <td className="px-4 py-3 text-muted-foreground">v{resource.version}</td>
                          <td className="px-4 py-3 text-muted-foreground">
                            <SmartTime date={resource.updated_at} />
                          </td>
                          <td className="px-4 py-3">
                            <ChevronRight
                              aria-hidden="true"
                              className="h-4 w-4 text-muted-foreground/40 transition-colors group-hover:text-muted-foreground"
                            />
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
            <Pagination page={page} totalPages={totalPages} onPageChange={setPage} />
          </>
        )}
      </div>

      <ConfirmDialog
        open={bulkDeleteOpen}
        onOpenChange={setBulkDeleteOpen}
        title="Delete selected resources"
        description={`Are you sure you want to delete ${selectedIds.size} resource${selectedIds.size === 1 ? '' : 's'}? This action cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleBulkDelete()}
        loading={bulkDeleting}
      />

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
                    required
                    aria-required="true"
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
                    htmlFor="new-resource-project"
                    className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                  >
                    Project
                  </label>
                  <input
                    id="new-resource-project"
                    type="text"
                    value={newProject}
                    onChange={(e) => setNewProject(e.target.value)}
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
                  className="btn-press inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {submitting && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                  )}
                  Create Resource
                </button>
              </div>
            </form>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>

      <Dialog.Root
        open={pasteOpen}
        onOpenChange={(v) => {
          setPasteOpen(v)
          if (!v) setPasteYaml('')
        }}
      >
        <Dialog.Portal>
          <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
          <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[560px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
            <div className="flex items-center justify-between border-b px-5 py-4">
              <div>
                <Dialog.Title className="text-lg font-semibold">Paste YAML</Dialog.Title>
                <Dialog.Description className="mt-0.5 text-sm text-muted-foreground">
                  Paste one or more YAML resource documents separated by{' '}
                  <code className="rounded bg-muted px-1 font-mono text-xs">---</code>
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

            <div className="space-y-4 p-5">
              <textarea
                value={pasteYaml}
                onChange={(e) => setPasteYaml(e.target.value)}
                disabled={pasteImporting}
                placeholder={
                  'apiVersion: blackbeard/v1alpha1\nkind: Agent\nmetadata:\n  name: my-agent\nspec:\n  role: researcher\n  goal: Find information\n  backstory: An experienced researcher'
                }
                spellCheck={false}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
                aria-label="YAML content"
                className="h-64 w-full resize-y rounded-md border bg-background px-3 py-2.5 font-mono text-xs leading-relaxed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
              />
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
                  type="button"
                  onClick={() => void handlePasteImport()}
                  disabled={pasteImporting || !pasteYaml.trim()}
                  aria-busy={pasteImporting}
                  className="btn-press inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {pasteImporting && (
                    <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                  )}
                  Import YAML
                </button>
              </div>
            </div>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  )
}
