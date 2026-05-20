import { useEffect, useState, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { Trash2, Pencil, Save, X, AlertTriangle, Play, Info } from 'lucide-react'
import { modKey } from '@/lib/platform'

import { CodeBlock } from '@/components/ui/CodeBlock'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { api } from '@/api/client'
import { cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks'
import { resourceToYaml, parseYaml } from '@/lib/yaml'
import { formatDate } from '@/lib/formatters'
import { KindBadge } from '@/components/ui/KindBadge'
import { PLURAL_TO_KIND } from '@/lib/kinds'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { RunDialog, type RunParams } from '@/components/studio/RunDialog'
import { Spinner } from '@/components/ui/Spinner'
import { useToastStore } from '@/stores/toastStore'

/* ------------------------------------------------------------------ */
/* Shared primitives                                                   */
/* ------------------------------------------------------------------ */

function InlineAlert({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div
      role="alert"
      className="mb-4 flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <AlertTriangle className="h-4 w-4 shrink-0" />
      {message}
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Spec display                                                        */
/* ------------------------------------------------------------------ */

function SpecValue({ value }: { value: unknown }): React.ReactElement {
  if (value === null || value === undefined) {
    return <span className="text-xs italic text-muted-foreground">null</span>
  }
  if (typeof value === 'boolean') {
    return (
      <span
        className={
          value
            ? 'font-medium text-emerald-600 dark:text-emerald-400'
            : 'font-medium text-red-500 dark:text-red-400'
        }
      >
        {String(value)}
      </span>
    )
  }
  if (typeof value === 'number') {
    return <span className="font-mono text-xs text-blue-600 dark:text-blue-400">{value}</span>
  }
  if (typeof value === 'string') {
    const refMatch = value.match(/^ref:([a-z-]+)\/([a-z0-9][a-z0-9-]*)$/)
    if (refMatch) {
      const [, kindPlural, refName] = refMatch
      return (
        <Link
          to={`/resources/${kindPlural}/${refName}`}
          className="font-mono text-xs text-primary hover:underline"
        >
          {value}
        </Link>
      )
    }
    if (value.includes('\n')) {
      return (
        <pre className="overflow-x-auto whitespace-pre-wrap rounded-md border bg-muted/60 p-2 font-mono text-xs">
          {value}
        </pre>
      )
    }
    return <span className="break-all">{value}</span>
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-xs italic text-muted-foreground">[]</span>
    return (
      <ul className="space-y-1">
        {(value as unknown[]).map((item: unknown, idx: number) => (
          <li key={idx} className="flex items-start gap-1.5">
            <span className="mt-0.5 select-none text-muted-foreground/60">•</span>
            <SpecValue value={item} />
          </li>
        ))}
      </ul>
    )
  }
  if (typeof value === 'object') {
    return (
      <div className="space-y-1.5 border-l-2 border-border pl-3">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="flex items-start gap-2">
            <span className="min-w-[80px] shrink-0 text-xs font-medium text-muted-foreground">
              {k}
            </span>
            <SpecValue value={v} />
          </div>
        ))}
      </div>
    )
  }
  return <span>{JSON.stringify(value)}</span>
}

function prettifyKey(key: string): string {
  return key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

function SpecDisplay({ spec }: { spec: Record<string, unknown> }) {
  const entries = Object.entries(spec)
  if (entries.length === 0) {
    return <p className="text-sm italic text-muted-foreground">No spec fields defined.</p>
  }
  return (
    <dl className="divide-y divide-border">
      {entries.map(([key, value]) => (
        <div
          key={key}
          className="grid grid-cols-1 items-start gap-2 py-3 sm:grid-cols-[180px_1fr] sm:gap-6"
        >
          <dt className="text-sm font-medium text-muted-foreground">{prettifyKey(key)}</dt>
          <dd className="min-w-0 text-sm">
            <SpecValue value={value} />
          </dd>
        </div>
      ))}
    </dl>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function ResourceDetail() {
  const { kindPlural = '', name = '' } = useParams<{ kindPlural: string; name: string }>()
  const navigate = useNavigate()
  const deleteResource = useResourceStore((s) => s.deleteResource)
  const updateResource = useResourceStore((s) => s.updateResource)
  const toasts = useToastStore()

  const [resource, setResource] = useState<Resource | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [yamlContent, setYamlContent] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('spec')
  const [showRunDialog, setShowRunDialog] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [runLoading, setRunLoading] = useState(false)
  const yamlEditorRef = useRef<HTMLTextAreaElement>(null)
  const deleteErrorTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (deleteErrorTimerRef.current) clearTimeout(deleteErrorTimerRef.current)
    }
  }, [])

  const loadResource = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<Resource>(`/api/v1/${kindPlural}/${name}`)
      setResource(res)
      setYamlContent(resourceToYaml(res))
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load resource'))
    } finally {
      setLoading(false)
    }
  }, [kindPlural, name])

  useEffect(() => {
    void loadResource()
  }, [loadResource])

  useDocumentTitle(resource ? resource.metadata.name : 'Resource')

  const handleEdit = () => {
    if (resource) setYamlContent(resourceToYaml(resource))
    setEditMode(true)
    setActiveTab('yaml')
    setSaveError(null)
    requestAnimationFrame(() => yamlEditorRef.current?.focus())
  }

  const handleCancelEdit = () => {
    if (resource) setYamlContent(resourceToYaml(resource))
    setEditMode(false)
    setSaveError(null)
  }

  const handleSave = async () => {
    if (!resource) return
    setSaveError(null)
    setSaving(true)
    try {
      const parsed = parseYaml(yamlContent)
      const spec = (parsed['spec'] as Record<string, unknown>) ?? {}
      const meta = parsed['metadata'] as
        | { name?: string; namespace?: string; labels?: Record<string, string> }
        | undefined
      const updated = await updateResource(kindPlural, name, {
        spec,
        metadata: {
          name: meta?.name ?? resource.metadata.name,
          namespace: meta?.namespace ?? resource.metadata.namespace,
          labels: meta?.labels ?? resource.metadata.labels,
        },
        version: resource.version,
      })
      setResource(updated)
      setYamlContent(resourceToYaml(updated))
      setEditMode(false)
      toasts.success(`Resource "${name}" saved`)
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to save resource')
      setSaveError(message)
      toasts.error(message)
    } finally {
      setSaving(false)
    }
  }

  const handleSaveRef = useRef(handleSave)
  handleSaveRef.current = handleSave

  useEffect(() => {
    if (!editMode) return
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 's') {
        e.preventDefault()
        void handleSaveRef.current()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [editMode])

  const handleDelete = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteResource(kindPlural, name)
      toasts.success(`Resource "${name}" deleted`)
      void navigate('/resources')
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to delete resource')
      setDeleteError(message)
      toasts.error(message)
      setDeleteOpen(false)
      if (deleteErrorTimerRef.current) clearTimeout(deleteErrorTimerRef.current)
      deleteErrorTimerRef.current = setTimeout(() => setDeleteError(null), 8000)
    } finally {
      setDeleting(false)
    }
  }

  const handleRun = async (params: RunParams) => {
    setRunError(null)
    setRunLoading(true)
    try {
      let inputs: Record<string, unknown> = {}
      try {
        inputs = JSON.parse(params.inputs) as Record<string, unknown>
      } catch {
        setRunError('Invalid JSON input')
        setRunLoading(false)
        return
      }
      const ns = resource?.metadata.namespace ?? 'default'
      const nsParam = ns !== 'default' ? `?namespace=${encodeURIComponent(ns)}` : ''

      let result: { id: string }
      if (params.mode === 'train') {
        result = await api.post<{ id: string }>(`/api/v1/crews/${name}/train${nsParam}`, {
          inputs,
          n_iterations: params.iterations,
          filename: params.filename,
        })
      } else if (params.mode === 'test') {
        result = await api.post<{ id: string }>(`/api/v1/crews/${name}/test${nsParam}`, {
          inputs,
          n_iterations: params.iterations,
        })
      } else {
        result = await api.post<{ id: string }>(`/api/v1/crews/${name}/kickoff${nsParam}`, {
          inputs,
        })
      }
      void navigate(`/executions/${result.id}`)
    } catch (err) {
      setRunError(getErrorMessage(err, 'Run failed'))
    } finally {
      setRunLoading(false)
    }
  }

  /* ---- Loading / error states ---- */
  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div role="status" className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="md" className="text-muted-foreground" />
          <span className="text-sm">Loading resource…</span>
        </div>
      </div>
    )
  }

  if (error || !resource) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" aria-hidden="true" />
          <p className="font-medium">{error ?? 'Resource not found'}</p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <button
              onClick={() => void loadResource()}
              className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Retry
            </button>
            <Link
              to="/resources"
              className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Back to Resources
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-4xl p-6">
        {/* Breadcrumb */}
        <nav aria-label="Breadcrumb" className="mb-5">
          <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <li>
              <Link
                to="/resources"
                className="rounded transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Resources
              </Link>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">
              ›
            </li>
            <li>
              <span className="text-foreground/80">{PLURAL_TO_KIND[kindPlural] ?? kindPlural}</span>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">
              ›
            </li>
            <li aria-current="page">
              <span className="font-medium text-foreground">{resource.metadata.name}</span>
            </li>
          </ol>
        </nav>

        {/* Header */}
        <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex flex-wrap items-center gap-3">
            <KindBadge kind={resource.kind} />
            <h1 className="text-2xl font-semibold tracking-tight">{resource.metadata.name}</h1>
            <span className="rounded-full border px-2 py-0.5 text-sm text-muted-foreground">
              v{resource.version}
            </span>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            {editMode ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
                <button
                  onClick={() => void handleSave()}
                  disabled={saving}
                  aria-busy={saving}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {saving ? (
                    <Spinner size="sm" className="text-current" />
                  ) : (
                    <Save className="h-3.5 w-3.5" />
                  )}
                  Save
                </button>
              </>
            ) : (
              <>
                {resource.kind === 'Crew' && (
                  <button
                    onClick={() => {
                      setShowRunDialog(true)
                      setRunError(null)
                    }}
                    className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-3 py-2 text-sm text-white transition-colors hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Run
                  </button>
                )}
                <button
                  onClick={handleEdit}
                  className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>
                <button
                  onClick={() => setDeleteOpen(true)}
                  className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </>
            )}
          </div>
        </div>

        {/* Metadata strip */}
        <div className="mb-6 flex flex-col gap-4 rounded-lg border bg-muted/20 px-4 py-3 text-sm text-muted-foreground sm:flex-row sm:flex-wrap sm:items-center sm:gap-6">
          {resource.metadata.namespace && resource.metadata.namespace !== 'default' && (
            <>
              <div>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
                  Namespace
                </span>
                <p className="mt-0.5 font-medium text-foreground">{resource.metadata.namespace}</p>
              </div>
              <div className="hidden h-8 w-px bg-border sm:block" />
            </>
          )}
          <div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
              API Version
            </span>
            <p className="mt-0.5 font-mono text-xs text-foreground">{resource.apiVersion}</p>
          </div>
          <div className="hidden h-8 w-px bg-border sm:block" />
          <div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
              Updated
            </span>
            <p className="mt-0.5 text-foreground">{formatDate(resource.updated_at)}</p>
          </div>
          {Object.keys(resource.metadata.labels ?? {}).length > 0 ? (
            <>
              <div className="hidden h-8 w-px bg-border sm:block" />
              <div>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
                  Labels
                </span>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  {Object.entries(resource.metadata.labels ?? {}).map(([k, v]) => (
                    <span
                      key={k}
                      className="inline-flex items-center rounded bg-secondary px-1.5 py-0.5 font-mono text-xs text-secondary-foreground"
                    >
                      {k}={v}
                    </span>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Delete error */}
        {deleteError && (
          <ErrorAlert
            message={deleteError}
            actionLabel="Dismiss"
            onAction={() => setDeleteError(null)}
            ariaLabel="Dismiss delete error"
            className="mb-4"
          />
        )}

        {/* Save error */}
        <InlineAlert message={saveError} />

        {/* Run error */}
        <InlineAlert message={runError} />

        {/* Tabs */}
        <TabsPrimitive.Root value={activeTab} onValueChange={setActiveTab}>
          <TabsPrimitive.List className="mb-6 flex gap-0 border-b">
            {['spec', 'yaml'].map((tab) => (
              <TabsPrimitive.Trigger
                key={tab}
                value={tab}
                className={cn(
                  '-mb-px border-b-2 px-4 py-2.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
                  'data-[state=active]:border-primary data-[state=active]:text-primary',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:text-foreground',
                )}
              >
                {tab === 'spec' ? 'Spec' : 'YAML'}
              </TabsPrimitive.Trigger>
            ))}
          </TabsPrimitive.List>

          <TabsPrimitive.Content value="spec">
            <div className="rounded-lg border bg-card p-4">
              <SpecDisplay spec={resource.spec} />
            </div>
          </TabsPrimitive.Content>

          <TabsPrimitive.Content value="yaml">
            {editMode && (
              <div
                id="yaml-edit-hint"
                className="mb-3 flex items-center gap-2 rounded-md bg-blue-50 p-2 text-sm text-blue-700 dark:bg-blue-950 dark:text-blue-300"
              >
                <Info className="h-4 w-4 shrink-0" />
                <span>Editing in YAML mode. Changes will be validated on save ({modKey}+S).</span>
              </div>
            )}
            <div
              className="overflow-hidden rounded-lg border"
              role="region"
              aria-label={editMode ? 'YAML editor' : 'YAML preview'}
            >
              {editMode ? (
                <textarea
                  ref={yamlEditorRef}
                  value={yamlContent}
                  onChange={(e) => setYamlContent(e.target.value)}
                  className="h-[500px] w-full resize-none bg-[#0d1117] p-4 font-mono text-sm text-slate-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                  spellCheck={false}
                  autoComplete="off"
                  autoCapitalize="off"
                  autoCorrect="off"
                  aria-label="YAML editor"
                  aria-describedby="yaml-edit-hint"
                />
              ) : (
                <CodeBlock code={yamlContent} language="yaml" className="max-h-[500px]" />
              )}
            </div>
            {!editMode && (
              <p className="mt-2 text-xs text-muted-foreground">
                Click{' '}
                <button
                  onClick={handleEdit}
                  className="underline underline-offset-2 transition-colors hover:text-foreground focus-visible:rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Edit
                </button>{' '}
                to modify this resource
              </p>
            )}
          </TabsPrimitive.Content>
        </TabsPrimitive.Root>
      </div>

      {/* Delete dialog */}
      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={(v) => {
          if (!v) {
            setDeleteOpen(false)
            setDeleteError(null)
          }
        }}
        title="Delete resource"
        description={`Are you sure you want to delete "${resource.metadata.name}"? This action cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleDelete()}
        loading={deleting}
      />
      {/* Run dialog */}
      <RunDialog
        open={showRunDialog}
        onOpenChange={setShowRunDialog}
        crewName={resource.metadata.name}
        onRun={(params) => void handleRun(params)}
        loading={runLoading}
      />
    </div>
  )
}
