import { useEffect, useState, useRef } from 'react'
import { useDocumentTitle } from '@/lib/hooks'
import { API_VERSION } from '@/lib/kinds'
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
  Check,
  Settings,
} from 'lucide-react'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { PageHeader } from '@/components/ui/PageHeader'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Provider badge                                                      */
/* ------------------------------------------------------------------ */

const PROVIDER_CLASSES: Record<string, string> = {
  openai:
    'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
  anthropic:
    'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900 dark:text-violet-300 dark:border-violet-800',
  vertex_ai:
    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  azure:
    'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-900 dark:text-sky-300 dark:border-sky-800',
  ollama:
    'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900 dark:text-orange-300 dark:border-orange-800',
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
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
        PROVIDER_CLASSES[provider] ??
          'border-gray-200 bg-gray-100 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300',
      )}
    >
      {label}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Model card                                                          */
/* ------------------------------------------------------------------ */

function ModelCard({ resource, onDelete }: { resource: Resource; onDelete: () => void }) {
  const spec = resource.spec as {
    provider?: string
    model?: string
    parameters?: { temperature?: number; max_tokens?: number }
    vertex?: { project?: string; location?: string }
  }

  return (
    <div className="group flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-shadow hover:shadow-md">
      {/* Header */}
      <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 rounded-md border border-amber-200 bg-amber-100 p-1.5">
              <Cpu className="h-4 w-4 text-amber-600" />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold">{resource.metadata.name}</p>
              {resource.metadata.namespace && resource.metadata.namespace !== 'default' && (
                <p className="text-xs text-muted-foreground">{resource.metadata.namespace}</p>
              )}
            </div>
          </div>
          <button
            onClick={(e) => {
              e.stopPropagation()
              onDelete()
            }}
            className="shrink-0 rounded p-1.5 text-muted-foreground opacity-40 transition-all hover:bg-destructive/10 hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100"
            title="Delete connection"
            aria-label="Delete connection"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 space-y-3 px-4 py-3">
        {spec.provider && (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              <Server className="h-3 w-3" />
              Provider
            </span>
            <ProviderBadge provider={spec.provider} />
          </div>
        )}

        {spec.model && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Model</span>
            <span
              className="max-w-[160px] truncate font-mono text-xs font-medium"
              title={spec.model}
            >
              {spec.model}
            </span>
          </div>
        )}

        {spec.parameters && (
          <div className="space-y-1.5 border-t pt-1">
            {spec.parameters.temperature !== undefined && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Thermometer className="h-3 w-3" />
                  Temperature
                </span>
                <span className="font-mono text-xs">{spec.parameters.temperature}</span>
              </div>
            )}
            {spec.parameters.max_tokens !== undefined && (
              <div className="flex items-center justify-between">
                <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Hash className="h-3 w-3" />
                  Max tokens
                </span>
                <span className="font-mono text-xs">
                  {spec.parameters.max_tokens.toLocaleString()}
                </span>
              </div>
            )}
          </div>
        )}

        {spec.vertex?.project && (
          <div className="flex items-center justify-between border-t pt-1">
            <span className="text-xs text-muted-foreground">GCP Project</span>
            <span className="max-w-[160px] truncate font-mono text-xs">{spec.vertex.project}</span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t bg-muted/10 px-4 py-2">
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

  const set =
    (field: keyof AddModelForm) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
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
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border bg-card shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold">Add LLM Connection</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                Configure a new language model connection
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Form */}
          <form onSubmit={handleSubmit} className="space-y-4 p-5">
            <fieldset disabled={submitting} className="grid grid-cols-2 gap-4">
              <div className="col-span-2">
                <label htmlFor="model-name" className="mb-1.5 block text-xs font-medium">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  id="model-name"
                  required
                  aria-required="true"
                  type="text"
                  value={form.name}
                  onChange={set('name')}
                  placeholder="my-gpt4-connection"
                  className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                />
              </div>

              <div>
                <label htmlFor="model-provider" className="mb-1.5 block text-xs font-medium">
                  Provider
                </label>
                <select
                  id="model-provider"
                  value={form.provider}
                  onChange={set('provider')}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                >
                  {PROVIDER_OPTIONS.map((p) => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="model-model" className="mb-1.5 block text-xs font-medium">
                  Model <span className="text-destructive">*</span>
                </label>
                <input
                  id="model-model"
                  required
                  aria-required="true"
                  type="text"
                  value={form.model}
                  onChange={set('model')}
                  placeholder="gpt-4o"
                  className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                />
              </div>

              <div>
                <label htmlFor="model-temperature" className="mb-1.5 block text-xs font-medium">
                  Temperature
                </label>
                <input
                  id="model-temperature"
                  type="number"
                  min="0"
                  max="2"
                  step="0.1"
                  value={form.temperature}
                  onChange={set('temperature')}
                  aria-describedby="model-temperature-hint"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                />
                <p id="model-temperature-hint" className="mt-1 text-xs text-muted-foreground/70">
                  Range: 0.0 – 2.0
                </p>
              </div>

              <div>
                <label htmlFor="model-max-tokens" className="mb-1.5 block text-xs font-medium">
                  Max tokens
                </label>
                <input
                  id="model-max-tokens"
                  type="number"
                  min="1"
                  value={form.max_tokens}
                  onChange={set('max_tokens')}
                  aria-describedby="model-max-tokens-hint"
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring disabled:opacity-50"
                />
                <p id="model-max-tokens-hint" className="mt-1 text-xs text-muted-foreground/70">
                  Minimum 1
                </p>
              </div>
            </fieldset>

            {submitError && (
              <div
                role="alert"
                className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
              >
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {submitError}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
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
  const [successMessage, setSuccessMessage] = useState<string | null>(null)
  const successTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
    }
  }, [])

  const models = resources['llm-connections'] ?? []

  useDocumentTitle('Models')

  useEffect(() => {
    void fetchResources('llm-connections')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleAdd = async (form: AddModelForm) => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      await createResource({
        apiVersion: API_VERSION,
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
      setSuccessMessage(`Connection "${form.name}" created`)
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
      successTimerRef.current = setTimeout(() => setSuccessMessage(null), 5000)
    } catch (err) {
      setSubmitError((err as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    const name = deleteTarget
    setDeleting(true)
    try {
      await deleteResource('llm-connections', name)
      setDeleteTarget(null)
      setSuccessMessage(`Connection "${name}" deleted`)
      if (successTimerRef.current) clearTimeout(successTimerRef.current)
      successTimerRef.current = setTimeout(() => setSuccessMessage(null), 5000)
    } catch {
      // error already in store
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Models"
            description="LLM connections and providers"
            actions={
              <>
                <button
                  onClick={() => void fetchResources('llm-connections')}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  aria-label="Refresh models"
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
                  onClick={() => {
                    setSubmitError(null)
                    setAddOpen(true)
                  }}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-4 w-4" />
                  Add Connection
                </button>
              </>
            }
          />
        </div>

        {/* Success */}
        {successMessage && (
          <div
            role="status"
            aria-live="polite"
            className="mb-4 flex items-center gap-2 text-sm text-green-600 dark:text-green-400"
          >
            <Check className="h-4 w-4" />
            {successMessage}
            <button
              onClick={() => setSuccessMessage(null)}
              className="ml-auto rounded p-2 transition-colors hover:bg-green-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:hover:bg-green-900"
              aria-label="Dismiss success message"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          </div>
        )}

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchResources('llm-connections')}
            ariaLabel="Retry loading connections"
            className="mb-4"
          />
        )}

        {/* Content */}
        {loading && models.length === 0 ? (
          <TableSkeleton />
        ) : models.length === 0 ? (
          <div className="page-enter flex flex-col items-center justify-center py-16 text-center">
            <div
              aria-hidden="true"
              className="mb-4 text-muted-foreground/60 [&>svg]:h-12 [&>svg]:w-12"
            >
              <Settings />
            </div>
            <h2 className="text-sm font-medium text-foreground">No LLM connections</h2>
            <p className="mt-1 max-w-xs text-xs text-muted-foreground">
              Add an LLM connection to get started
            </p>
            <button
              onClick={() => {
                setSubmitError(null)
                setAddOpen(true)
              }}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Plus className="h-3.5 w-3.5" />
              Add Connection
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
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
        onSubmit={(form) => void handleAdd(form)}
        submitting={submitting}
        submitError={submitError}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(v) => {
          if (!v) setDeleteTarget(null)
        }}
        title="Delete connection"
        description={`Delete "${deleteTarget}"? This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleDelete()}
        loading={deleting}
      />
    </div>
  )
}
