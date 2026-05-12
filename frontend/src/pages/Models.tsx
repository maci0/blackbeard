import { useEffect, useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import {
  Plus,
  Trash2,
  Cpu,
  AlertTriangle,
  X,
  RefreshCw,
  Server,
  Thermometer,
  Hash,
} from 'lucide-react'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Provider badge                                                      */
/* ------------------------------------------------------------------ */

const PROVIDER_CLASSES: Record<string, string> = {
  openai: 'bg-emerald-100 text-emerald-700 border-emerald-200',
  anthropic: 'bg-violet-100 text-violet-700 border-violet-200',
  vertex_ai: 'bg-blue-100 text-blue-700 border-blue-200',
  azure: 'bg-sky-100 text-sky-700 border-sky-200',
  ollama: 'bg-orange-100 text-orange-700 border-orange-200',
}

const PROVIDER_DISPLAY: Record<string, string> = {
  openai: 'OpenAI',
  anthropic: 'Anthropic',
  vertex_ai: 'Google Vertex AI',
  azure: 'Azure OpenAI',
  ollama: 'Ollama (local)',
  other: 'Other',
}

function ProviderBadge({ provider }: { provider: string }) {
  const label = PROVIDER_DISPLAY[provider] ?? provider
  return (
    <span
      className={cn(
        'inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium border',
        PROVIDER_CLASSES[provider] ?? 'bg-gray-100 text-gray-600 border-gray-200',
      )}
    >
      {label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Model card                                                          */
/* ------------------------------------------------------------------ */

function ModelCard({
  resource,
  onDelete,
}: {
  resource: Resource
  onDelete: () => void
}) {
  const spec = resource.spec as {
    provider?: string
    model?: string
    parameters?: { temperature?: number; max_tokens?: number }
    vertex?: { project?: string; location?: string }
  }

  return (
    <div className="border rounded-lg bg-card shadow-sm hover:shadow-md transition-shadow group overflow-hidden flex flex-col">
      {/* Header */}
      <div className="px-4 pt-4 pb-3 border-b bg-muted/20">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <div className="p-1.5 rounded-md bg-amber-100 border border-amber-200 shrink-0">
              <Cpu className="h-4 w-4 text-amber-600" />
            </div>
            <div className="min-w-0">
              <p className="font-semibold text-sm truncate">{resource.metadata.name}</p>
              {resource.metadata.namespace && resource.metadata.namespace !== 'default' && (
                <p className="text-xs text-muted-foreground">
                  {resource.metadata.namespace}
                </p>
              )}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="opacity-0 group-hover:opacity-100 focus:opacity-100 focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none p-1.5 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-all shrink-0"
            title="Delete connection"
            aria-label="Delete connection"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="px-4 py-3 flex-1 space-y-3">
        {spec.provider && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground flex items-center gap-1.5">
              <Server className="h-3 w-3" />
              Provider
            </span>
            <ProviderBadge provider={spec.provider} />
          </div>
        )}

        {spec.model && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Model</span>
            <span className="text-xs font-mono font-medium truncate max-w-[160px]">
              {spec.model}
            </span>
          </div>
        )}

        {spec.parameters && (
          <div className="space-y-1.5 pt-1 border-t">
            {spec.parameters.temperature !== undefined && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Thermometer className="h-3 w-3" />
                  Temperature
                </span>
                <span className="text-xs font-mono">{spec.parameters.temperature}</span>
              </div>
            )}
            {spec.parameters.max_tokens !== undefined && (
              <div className="flex items-center justify-between">
                <span className="text-xs text-muted-foreground flex items-center gap-1.5">
                  <Hash className="h-3 w-3" />
                  Max tokens
                </span>
                <span className="text-xs font-mono">
                  {spec.parameters.max_tokens.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}

        {spec.vertex?.project && (
          <div className="flex items-center justify-between pt-1 border-t">
            <span className="text-xs text-muted-foreground">GCP Project</span>
            <span className="text-xs font-mono truncate max-w-[160px]">
              {spec.vertex.project}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 py-2 border-t bg-muted/10">
        <span className="text-xs text-muted-foreground">v{resource.version}</span>
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Add model dialog                                                    */
/* ------------------------------------------------------------------ */

interface AddModelForm {
  name: string
  provider: string
  model: string
  temperature: string
  max_tokens: string
}

const INITIAL_FORM: AddModelForm = {
  name: '',
  provider: 'openai',
  model: '',
  temperature: '0.7',
  max_tokens: '4096',
}

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'vertex_ai', label: 'Google Vertex AI' },
  { value: 'azure', label: 'Azure OpenAI' },
  { value: 'ollama', label: 'Ollama (local)' },
  { value: 'other', label: 'Other' },
]

function AddModelDialog({
  open,
  onOpenChange,
  onSubmit,
  submitting,
  submitError,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSubmit: (form: AddModelForm) => void
  submitting: boolean
  submitError: string | null
}) {
  const [form, setForm] = useState<AddModelForm>(INITIAL_FORM)

  const set = (field: keyof AddModelForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [field]: e.target.value }))

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSubmit(form)
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) setForm(INITIAL_FORM)
        onOpenChange(v)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[480px] max-w-[90vw] bg-card border rounded-xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b">
            <div>
              <Dialog.Title className="text-base font-semibold">Add LLM Connection</Dialog.Title>
              <Dialog.Description className="text-xs text-muted-foreground mt-0.5">
                Configure a new language model connection
              </Dialog.Description>
            </div>
            <Dialog.Close className="p-1.5 rounded hover:bg-accent transition-colors text-muted-foreground" aria-label="Close">
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="p-5 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label htmlFor="model-name" className="block text-xs font-medium mb-1.5">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  id="model-name"
                  required
                  type="text"
                  value={form.name}
                  onChange={set('name')}
                  placeholder="my-gpt4-connection"
                  className="w-full px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                />
              </div>

              <div>
                <label htmlFor="model-provider" className="block text-xs font-medium mb-1.5">Provider</label>
                <select
                  id="model-provider"
                  value={form.provider}
                  onChange={set('provider')}
                  className="w-full px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {PROVIDER_OPTIONS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="model-model" className="block text-xs font-medium mb-1.5">
                  Model <span className="text-destructive">*</span>
                </label>
                <input
                  id="model-model"
                  required
                  type="text"
                  value={form.model}
                  onChange={set('model')}
                  placeholder="gpt-4o"
                  className="w-full px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring font-mono"
                />
              </div>

              <div>
                <label htmlFor="model-temperature" className="block text-xs font-medium mb-1.5">Temperature</label>
                <input
                  id="model-temperature"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={form.temperature}
                  onChange={set('temperature')}
                  className="w-full px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground/70 mt-1">Range: 0.0 – 2.0</p>
              </div>

              <div>
                <label htmlFor="model-max-tokens" className="block text-xs font-medium mb-1.5">Max tokens</label>
                <input
                  id="model-max-tokens"
                  type="number"
                  min="1"
                  value={form.max_tokens}
                  onChange={set('max_tokens')}
                  className="w-full px-3 py-2 text-sm border rounded-md bg-background focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="text-xs text-muted-foreground/70 mt-1">Minimum 1</p>
              </div>
            </div>

            {submitError && (
              <div role="alert" className="p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {submitError}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="px-4 py-2 text-sm border rounded-md hover:bg-accent transition-colors"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-1.5 px-4 py-2 text-sm bg-primary text-primary-foreground rounded-md hover:opacity-90 transition-opacity disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-white" />}
                Add connection
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Models() {
  const { resources, loading, error, fetchResources, createResource, deleteResource } =
    useResourceStore()

  const [addOpen, setAddOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)

  const models = resources['llm-connections'] ?? []

  useEffect(() => {
    document.title = 'LLM Connections | Blackbeard'
    return () => { document.title = 'Blackbeard' }
  }, [])

  useEffect(() => {
    fetchResources('llm-connections')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAdd = async (form: AddModelForm) => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await createResource({
        apiVersion: 'blackbeard/v1',
        kind: 'LLMConnection',
        metadata: { name: form.name, namespace: 'default' },
        spec: {
          provider: form.provider,
          model: form.model,
          parameters: {
            temperature: parseFloat(form.temperature),
            max_tokens: parseInt(form.max_tokens, 10),
          },
        },
      })
      setAddOpen(false)
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteResource('llm-connections', deleteTarget)
      setDeleteTarget(null)
    } catch {
      // error already in store
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="flex-1 overflow-auto">
      <div className="p-6 max-w-7xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">LLM Connections</h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Manage LLM connection configurations
            </p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => fetchResources('llm-connections')}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-sm border rounded-md bg-background hover:bg-accent transition-colors"
              aria-label="Refresh models"
            >
              <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin motion-reduce:animate-none')} />
              Refresh
            </button>
            <button
              onClick={() => setAddOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Plus className="h-4 w-4" />
              Add Connection
            </button>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div role="alert" className="mb-4 p-3 rounded-md bg-destructive/10 border border-destructive/20 text-sm text-destructive flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0" />
            {error}
          </div>
        )}

        {/* Loading */}
        {loading && models.length === 0 ? (
          <div className="flex items-center justify-center py-24">
            <div className="flex items-center gap-2 text-muted-foreground">
              <Spinner size="sm" className="text-muted-foreground" />
              <span className="text-sm">Loading connections…</span>
            </div>
          </div>
        ) : models.length === 0 ? (
          <div className="border-2 border-dashed rounded-xl flex flex-col items-center justify-center py-24 px-6 text-center">
            <div className="p-4 rounded-full bg-muted mb-4">
              <Cpu className="h-8 w-8 text-muted-foreground/50" />
            </div>
            <p className="font-medium text-muted-foreground mb-1">No LLM connections</p>
            <p className="text-sm text-muted-foreground/70 mb-4">
              Add your first model connection to get started
            </p>
            <button
              onClick={() => setAddOpen(true)}
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-md text-sm font-medium hover:opacity-90 transition-opacity"
            >
              <Plus className="h-4 w-4" />
              Add Connection
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {models.map((resource) => (
              <ModelCard
                key={resource.id}
                resource={resource}
                onDelete={() => setDeleteTarget(resource.metadata.name)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Dialogs */}
      <AddModelDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        onSubmit={handleAdd}
        submitting={submitting}
        submitError={submitError}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => { if (!v) setDeleteTarget(null) }}
        title="Delete connection"
        description={`Delete "${deleteTarget}"? This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={handleDelete}
        loading={deleting}
      />
    </div>
  )
}
