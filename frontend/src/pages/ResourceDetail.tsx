import { useEffect, useState, useCallback, useRef, lazy, Suspense } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import * as TabsPrimitive from '@radix-ui/react-tabs'
import { Trash2, Pencil, Save, X, AlertTriangle, Play, Check, Info } from 'lucide-react'

const Editor = lazy(() => import('@monaco-editor/react'))
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { api } from '@/api/client'
import { cn } from '@/lib/utils'
import { useDarkMode, useDocumentTitle } from '@/lib/hooks'
import { resourceToYaml, parseYaml } from '@/lib/yaml'
import { formatDate } from '@/lib/formatters'
import { KindBadge } from '@/components/ui/KindBadge'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { RunDialog } from '@/components/studio/RunDialog'
import { Spinner } from '@/components/ui/Spinner'

/* ------------------------------------------------------------------ */
/* Shared primitives                                                   */
/* ------------------------------------------------------------------ */

function InlineAlert({ message }: { message: string | null }) {
  if (!message) return null
  return (
    <div role="alert" className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center gap-2">
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
    return <span className="text-muted-foreground italic text-xs">null</span>
  }
  if (typeof value === 'boolean') {
    return (
      <span className={value ? 'text-emerald-600 font-medium' : 'text-red-500 font-medium'}>
        {String(value)}
      </span>
    )
  }
  if (typeof value === 'number') {
    return <span className="text-blue-600 font-mono text-xs">{value}</span>
  }
  if (typeof value === 'string') {
    const refMatch = value.match(/^ref:([a-z-]+)\/([a-z0-9][a-z0-9-]*)$/)
    if (refMatch) {
      const [, kindPlural, refName] = refMatch
      return (
        <Link
          to={`/resources/${kindPlural}/${refName}`}
          className="text-primary hover:underline font-mono text-xs"
        >
          {value}
        </Link>
      )
    }
    if (value.includes('\n')) {
      return (
        <pre className="text-xs bg-muted/60 rounded-md p-2 overflow-x-auto whitespace-pre-wrap font-mono border">
          {value}
        </pre>
      )
    }
    return <span className="break-all">{value}</span>
  }
  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-muted-foreground italic text-xs">[]</span>
    return (
      <ul className="space-y-1">
        {value.map((item, idx) => (
          <li key={idx} className="flex items-start gap-1.5">
            <span className="text-muted-foreground/60 mt-0.5 select-none">•</span>
            <SpecValue value={item} />
          </li>
        ))}
      </ul>
    )
  }
  if (typeof value === 'object') {
    return (
      <div className="border-l-2 border-border pl-3 space-y-1.5">
        {Object.entries(value as Record<string, unknown>).map(([k, v]) => (
          <div key={k} className="flex gap-2 items-start">
            <span className="text-xs font-medium text-muted-foreground shrink-0 min-w-[80px]">
              {k}
            </span>
            <SpecValue value={v} />
          </div>
        ))}
      </div>
    )
  }
  return <span>{String(value)}</span>
}

function prettifyKey(key: string): string {
  return key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function SpecDisplay({ spec }: { spec: Record<string, unknown> }) {
  const entries = Object.entries(spec)
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground italic">No spec fields defined.</p>
  }
  return (
    <dl className="divide-y divide-border">
      {entries.map(([key, value]) => (
        <div key={key} className="grid grid-cols-[180px_1fr] gap-6 py-3 items-start">
          <dt className="text-sm font-medium text-muted-foreground">{prettifyKey(key)}</dt>
          <dd className="text-sm min-w-0">
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
  const { deleteResource, updateResource } = useResourceStore()

  const [resource, setResource] = useState<Resource | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editMode, setEditMode] = useState(false)
  const [yamlContent, setYamlContent] = useState('')
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('spec')
  const [showRunDialog, setShowRunDialog] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const isDark = useDarkMode()
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => { if (saveTimerRef.current) clearTimeout(saveTimerRef.current) }
  }, [])

  const loadResource = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await api.get<Resource>(`/api/v1/${kindPlural}/${name}`)
      setResource(res)
      setYamlContent(resourceToYaml(res))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }, [kindPlural, name])

  useEffect(() => {
    loadResource()
  }, [loadResource])

  useDocumentTitle(resource ? resource.metadata.name : 'Resource')

  const handleEdit = () => {
    if (resource) setYamlContent(resourceToYaml(resource))
    setEditMode(true)
    setActiveTab('yaml')
    setSaveError(null)
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
          name: (meta?.name as string) ?? resource.metadata.name,
          namespace: (meta?.namespace as string) ?? resource.metadata.namespace,
          labels: (meta?.labels as Record<string, string>) ?? resource.metadata.labels,
        },
        version: resource.version,
      })
      setResource(updated)
      setYamlContent(resourceToYaml(updated))
      setEditMode(false)
      setSaveSuccess(true)
      saveTimerRef.current = setTimeout(() => setSaveSuccess(false), 5000)
    } catch (err) {
      setSaveError((err as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    setDeleting(true)
    setDeleteError(null)
    try {
      await deleteResource(kindPlural, name)
      navigate('/resources')
    } catch (err) {
      setDeleteError((err as Error).message)
    } finally {
      setDeleting(false)
    }
  }

  const handleRun = async (rawInputs: string) => {
    setRunError(null)
    try {
      const inputs = JSON.parse(rawInputs) as Record<string, unknown>
      const result = await api.post<{ id: string }>(`/api/v1/crews/${name}/kickoff`, { inputs })
      navigate(`/executions/${result.id}`)
    } catch (err) {
      setRunError((err as Error).message)
    }
  }

  /* ---- Loading / error states ---- */
  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="md" className="text-muted-foreground" />
          <span className="text-sm">Loading resource…</span>
        </div>
      </div>
    )
  }

  if (error || !resource) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="h-8 w-8 text-destructive mx-auto mb-3" />
          <p className="font-medium">{error ?? 'Resource not found'}</p>
          <div className="flex items-center gap-2 justify-center mt-4">
            <button
              onClick={loadResource}
              className="px-4 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
            >
              Retry
            </button>
            <Link
              to="/resources"
              className="px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 transition-opacity"
            >
              Back to Resources
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-4xl mx-auto">

        {/* Breadcrumb */}
        <nav aria-label="Breadcrumb" className="mb-5">
          <ol className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <li>
              <Link to="/resources" className="hover:text-foreground transition-colors">
                Resources
              </Link>
            </li>
            <li aria-hidden="true" className="text-muted-foreground/40">›</li>
            <li>
              <span className="text-foreground font-medium">{resource.metadata.name}</span>
            </li>
          </ol>
        </nav>

        {/* Header */}
        <div className="flex items-start justify-between gap-4 mb-6">
          <div className="flex items-center gap-3 flex-wrap">
            <KindBadge kind={resource.kind} />
            <h1 className="text-2xl font-semibold tracking-tight">{resource.metadata.name}</h1>
            <span className="text-sm text-muted-foreground border rounded-full px-2 py-0.5">
              v{resource.version}
            </span>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {editMode ? (
              <>
                <button
                  onClick={handleCancelEdit}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
                >
                  <X className="h-3.5 w-3.5" />
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={saving}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 transition-opacity disabled:opacity-50"
                >
                  {saving ? (
                    <Spinner size="sm" className="text-white" />
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
                    onClick={() => { setShowRunDialog(true); setRunError(null) }}
                    className="inline-flex items-center gap-1.5 px-3 py-2 text-sm bg-emerald-600 text-white rounded-md hover:bg-emerald-700 transition-colors"
                  >
                    <Play className="h-3.5 w-3.5" />
                    Run
                  </button>
                )}
                <button
                  onClick={handleEdit}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
                >
                  <Pencil className="h-3.5 w-3.5" />
                  Edit
                </button>
                <button
                  onClick={() => setDeleteOpen(true)}
                  className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border border-destructive/30 text-destructive rounded-md hover:bg-destructive/10 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  Delete
                </button>
              </>
            )}
          </div>
        </div>

        {/* Metadata strip */}
        <div className="flex flex-wrap items-center gap-6 mb-6 text-sm text-muted-foreground border rounded-lg px-4 py-3 bg-muted/20">
          {resource.metadata.namespace && resource.metadata.namespace !== 'default' && (
            <>
              <div>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
                  Namespace
                </span>
                <p className="font-medium text-foreground mt-0.5">
                  {resource.metadata.namespace}
                </p>
              </div>
              <div className="w-px h-8 bg-border" />
            </>
          )}
          <div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
              API Version
            </span>
            <p className="font-mono text-xs text-foreground mt-0.5">{resource.apiVersion}</p>
          </div>
          <div className="w-px h-8 bg-border" />
          <div>
            <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
              Updated
            </span>
            <p className="text-foreground mt-0.5">
              {formatDate(resource.updated_at)}
            </p>
          </div>
          {Object.keys(resource.metadata.labels ?? {}).length > 0 ? (
            <>
              <div className="w-px h-8 bg-border" />
              <div>
                <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground/60">
                  Labels
                </span>
                <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                  {Object.entries(resource.metadata.labels ?? {}).map(([k, v]) => (
                    <span
                      key={k}
                      className="inline-flex items-center text-xs bg-secondary text-secondary-foreground rounded px-1.5 py-0.5 font-mono"
                    >
                      {k}={v}
                    </span>
                  ))}
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Save error */}
        <InlineAlert message={saveError} />

        {/* Save success */}
        {saveSuccess && (
          <div role="status" className="mb-4 flex items-center gap-2 text-sm text-green-600 dark:text-green-400">
            <Check className="h-4 w-4" />
            Saved successfully
            <button onClick={() => setSaveSuccess(false)} className="ml-auto p-0.5 rounded hover:bg-green-100 dark:hover:bg-green-900 transition-colors" aria-label="Dismiss">
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Run error */}
        <InlineAlert message={runError} />

        {/* Tabs */}
        <TabsPrimitive.Root value={activeTab} onValueChange={setActiveTab}>
          <TabsPrimitive.List className="flex gap-0 border-b mb-6">
            {['spec', 'yaml'].map((tab) => (
              <TabsPrimitive.Trigger
                key={tab}
                value={tab}
                className={cn(
                  'px-4 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors',
                  'data-[state=active]:border-primary data-[state=active]:text-primary',
                  'data-[state=inactive]:border-transparent data-[state=inactive]:text-muted-foreground data-[state=inactive]:hover:text-foreground',
                )}
              >
                {tab === 'spec' ? 'Spec' : 'YAML'}
              </TabsPrimitive.Trigger>
            ))}
          </TabsPrimitive.List>

          <TabsPrimitive.Content value="spec">
            <div className="border rounded-lg bg-card p-4">
              <SpecDisplay spec={resource.spec} />
            </div>
          </TabsPrimitive.Content>

          <TabsPrimitive.Content value="yaml">
            {editMode && (
              <div className="mb-3 p-2 rounded-md bg-blue-50 dark:bg-blue-950 text-sm text-blue-700 dark:text-blue-300 flex items-center gap-2">
                <Info className="h-4 w-4 shrink-0" />
                <span>Editing in YAML mode. Changes will be validated on save.</span>
              </div>
            )}
            <div className="border rounded-lg overflow-hidden" role="region" aria-label={editMode ? 'YAML editor' : 'YAML preview'}>
              <Suspense fallback={<div className="h-[500px] flex items-center justify-center"><Spinner /></div>}>
                <Editor
                  height="500px"
                  language="yaml"
                  value={yamlContent}
                  onChange={(v) => setYamlContent(v ?? '')}
                  options={{
                    readOnly: !editMode,
                    minimap: { enabled: false },
                    fontSize: 13,
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'on',
                    padding: { top: 12, bottom: 12 },
                    renderLineHighlight: editMode ? 'line' : 'none',
                    cursorStyle: editMode ? 'line' : 'underline',
                  }}
                  theme={isDark ? 'vs-dark' : 'vs'}
                />
              </Suspense>
            </div>
            {!editMode && (
              <p className="mt-2 text-xs text-muted-foreground">
                Click{' '}
                <button
                  onClick={handleEdit}
                  className="underline underline-offset-2 hover:text-foreground transition-colors"
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
        onConfirm={handleDelete}
        loading={deleting}
      />
      {deleteError && (
        <div
          role="alert"
          className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 max-w-sm w-full px-4 py-3 rounded-lg bg-destructive/10 border border-destructive/30 text-sm text-destructive shadow-lg flex items-center gap-2"
        >
          <AlertTriangle className="h-4 w-4 shrink-0" />
          {deleteError}
          <button onClick={() => setDeleteError(null)} className="ml-auto p-0.5 rounded hover:bg-destructive/10 transition-colors" aria-label="Dismiss error">
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {/* Run dialog */}
      <RunDialog
        open={showRunDialog}
        onOpenChange={setShowRunDialog}
        crewName={resource.metadata.name}
        onRun={handleRun}
      />
    </div>
  )
}
