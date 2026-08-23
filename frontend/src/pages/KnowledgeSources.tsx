import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useDeleteError } from '@/hooks/useDeleteError'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { API_VERSION, NAME_PATTERN } from '@/lib/kinds'
import * as Dialog from '@radix-ui/react-dialog'
import {
  BookOpen,
  Plus,
  Trash2,
  RefreshCw,
  X,
  AlertTriangle,
  FileText,
  Globe,
  FileSpreadsheet,
  FileJson,
  FileType,
  Type,
} from 'lucide-react'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { PageHeader } from '@/components/ui/PageHeader'
import { KnowledgeCardSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { SmartTime } from '@/components/ui/SmartTime'
import { cn, getErrorMessage } from '@/lib/utils'
import { useToastStore } from '@/stores/toastStore'

const SOURCE_TYPES = ['text', 'pdf', 'csv', 'json', 'excel', 'string', 'url'] as const
type SourceType = (typeof SOURCE_TYPES)[number]

const TYPE_CONFIG: Record<
  SourceType,
  { icon: React.ComponentType<{ className?: string }>; label: string; className: string }
> = {
  text: {
    icon: FileText,
    label: 'Text',
    className:
      'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  },
  pdf: {
    icon: FileType,
    label: 'PDF',
    className:
      'bg-red-100 text-red-700 border-red-200 dark:bg-red-900 dark:text-red-300 dark:border-red-800',
  },
  csv: {
    icon: FileSpreadsheet,
    label: 'CSV',
    className:
      'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300 dark:border-emerald-800',
  },
  json: {
    icon: FileJson,
    label: 'JSON',
    className:
      'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300 dark:border-amber-800',
  },
  excel: {
    icon: FileSpreadsheet,
    label: 'Excel',
    className:
      'bg-green-100 text-green-700 border-green-200 dark:bg-green-900 dark:text-green-300 dark:border-green-800',
  },
  string: {
    icon: Type,
    label: 'String',
    className:
      'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900 dark:text-violet-300 dark:border-violet-800',
  },
  url: {
    icon: Globe,
    label: 'URL',
    className:
      'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-900 dark:text-sky-300 dark:border-sky-800',
  },
}

function isSourceType(type: string): type is SourceType {
  return (SOURCE_TYPES as readonly string[]).includes(type)
}

function SourceTypeBadge({ type }: { type: string }) {
  if (!isSourceType(type)) {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-gray-200 bg-gray-100 px-2 py-0.5 text-xs font-medium text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300">
        {type}
      </span>
    )
  }
  const config = TYPE_CONFIG[type]
  const Icon = config.icon
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium',
        config.className,
      )}
    >
      <Icon className="h-3 w-3" />
      {config.label}
    </span>
  )
}

function KnowledgeSourceCard({ resource, onDelete }: { resource: Resource; onDelete: () => void }) {
  const spec = resource.spec as {
    type?: string
    description?: string
    file_paths?: string[]
    urls?: string[]
    content?: string
    chunk_size?: number
    chunk_overlap?: number
  }

  const sourceDetail =
    spec.urls && spec.urls.length > 0
      ? spec.urls[0]
      : spec.file_paths && spec.file_paths.length > 0
        ? spec.file_paths[0]
        : spec.content
          ? `${spec.content.slice(0, 80)}${spec.content.length > 80 ? '…' : ''}`
          : null

  const itemCount =
    spec.urls && spec.urls.length > 1
      ? `${spec.urls.length} URLs`
      : spec.file_paths && spec.file_paths.length > 1
        ? `${spec.file_paths.length} files`
        : null

  return (
    <div className="group relative flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg">
      <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 rounded-md border border-indigo-200 bg-indigo-100 p-1.5 dark:border-indigo-800 dark:bg-indigo-900/50">
              <BookOpen
                className="h-4 w-4 text-indigo-600 dark:text-indigo-400"
                aria-hidden="true"
              />
            </div>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold" title={resource.metadata.name}>
                <Link
                  to={`/resources/knowledge-sources/${resource.metadata.name}`}
                  className="after:absolute after:inset-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring"
                >
                  {resource.metadata.name}
                </Link>
              </p>
              {resource.metadata.project && resource.metadata.project !== 'default' && (
                <p className="text-xs text-muted-foreground">{resource.metadata.project}</p>
              )}
            </div>
          </div>
          <div className="relative z-10 flex shrink-0 gap-1">
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onDelete()
              }}
              onKeyDown={(e) => e.stopPropagation()}
              className="flex h-[44px] w-[44px] shrink-0 items-center justify-center rounded text-muted-foreground transition-all hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:opacity-0 md:group-focus-within:opacity-100 md:group-hover:opacity-100"
              title={`Delete ${resource.metadata.name}`}
              aria-label={`Delete knowledge source ${resource.metadata.name}`}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2.5 px-4 py-3">
        {spec.type && (
          <div className="flex items-center justify-between">
            <span className="text-xs text-muted-foreground">Type</span>
            <SourceTypeBadge type={spec.type} />
          </div>
        )}

        {spec.description && (
          <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">
            {spec.description}
          </p>
        )}

        {sourceDetail && (
          <div>
            <p className="mb-0.5 text-xs text-muted-foreground/70">
              {spec.urls && spec.urls.length > 0
                ? 'URL'
                : spec.file_paths && spec.file_paths.length > 0
                  ? 'File'
                  : 'Content'}
            </p>
            <p
              className="truncate rounded bg-muted/50 px-1.5 py-0.5 font-mono text-xs text-foreground/80"
              title={sourceDetail}
            >
              {sourceDetail}
            </p>
          </div>
        )}

        {itemCount && <p className="text-xs text-muted-foreground">{itemCount}</p>}

        {(spec.chunk_size || spec.chunk_overlap) && (
          <div className="flex gap-3 border-t pt-1">
            {spec.chunk_size && (
              <span className="text-xs text-muted-foreground">Chunk: {spec.chunk_size}</span>
            )}
            {spec.chunk_overlap !== undefined && (
              <span className="text-xs text-muted-foreground">Overlap: {spec.chunk_overlap}</span>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between border-t bg-muted/10 px-4 py-2.5">
        <SmartTime date={resource.created_at} />
        <span className="text-xs text-muted-foreground">v{resource.version}</span>
      </div>
    </div>
  )
}

interface AddKnowledgeSourceForm {
  name: string
  type: SourceType
  source: string
  description: string
}

const INITIAL_FORM: AddKnowledgeSourceForm = {
  name: '',
  type: 'text',
  source: '',
  description: '',
}

function AddKnowledgeSourceDialog({
  open,
  onOpenChange,
  onSubmit,
  submitting,
  submitError,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  onSubmit: (form: AddKnowledgeSourceForm) => void
  submitting: boolean
  submitError: string | null
}) {
  const [form, setForm] = useState<AddKnowledgeSourceForm>(INITIAL_FORM)
  const [validationError, setValidationError] = useState<string | null>(null)

  const set =
    (field: keyof AddKnowledgeSourceForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
      setForm((f) => ({ ...f, [field]: e.target.value }))
      setValidationError(null)
    }

  const isUrlType = form.type === 'url'
  const isStringType = form.type === 'string'
  const sourceLabel = isUrlType ? 'URL' : isStringType ? 'Content' : 'File path'
  const sourcePlaceholder = isUrlType
    ? 'https://example.com/docs'
    : isStringType
      ? 'Paste your content here...'
      : 'data/my-file.pdf'

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setValidationError('Name is required.')
      return
    }
    if (!form.source.trim() && !isStringType) {
      setValidationError(`${sourceLabel} is required.`)
      return
    }
    setValidationError(null)
    onSubmit(form)
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (!v) setForm(INITIAL_FORM)
        setValidationError(null)
        onOpenChange(v)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border bg-card shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold">Add Knowledge Source</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                Configure a knowledge source for RAG-enabled agents
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <form onSubmit={handleSubmit} noValidate className="space-y-4 p-5">
            <fieldset disabled={submitting} aria-busy={submitting} className="space-y-4">
              <div>
                <label htmlFor="ks-name" className="mb-1.5 block text-xs font-medium">
                  Name <span className="text-destructive">*</span>
                </label>
                <input
                  id="ks-name"
                  required
                  aria-required="true"
                  type="text"
                  value={form.name}
                  onChange={set('name')}
                  placeholder="my-knowledge-source"
                  autoComplete="off"
                  autoFocus
                  pattern={NAME_PATTERN}
                  title="Lowercase letters, numbers, and hyphens only"
                  aria-describedby="ks-name-hint"
                  className="w-full rounded-md border bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
                <p id="ks-name-hint" className="mt-1 text-xs text-muted-foreground">
                  Lowercase letters, numbers, and hyphens only
                </p>
              </div>

              <div>
                <label htmlFor="ks-type" className="mb-1.5 block text-xs font-medium">
                  Source Type <span className="text-destructive">*</span>
                </label>
                <select
                  id="ks-type"
                  value={form.type}
                  onChange={set('type')}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                >
                  {SOURCE_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {TYPE_CONFIG[t].label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="ks-source" className="mb-1.5 block text-xs font-medium">
                  {sourceLabel} {!isStringType && <span className="text-destructive">*</span>}
                </label>
                {isStringType ? (
                  <textarea
                    id="ks-source"
                    value={form.source}
                    onChange={set('source')}
                    placeholder={sourcePlaceholder}
                    spellCheck={false}
                    autoComplete="off"
                    autoCapitalize="off"
                    autoCorrect="off"
                    className="h-24 w-full resize-none rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  />
                ) : (
                  <input
                    id="ks-source"
                    type="text"
                    value={form.source}
                    onChange={set('source')}
                    placeholder={sourcePlaceholder}
                    autoComplete="off"
                    spellCheck={false}
                    className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                  />
                )}
              </div>

              <div>
                <label htmlFor="ks-description" className="mb-1.5 block text-xs font-medium">
                  Description
                </label>
                <textarea
                  id="ks-description"
                  value={form.description}
                  onChange={set('description')}
                  placeholder="What this knowledge source contains..."
                  spellCheck
                  autoComplete="off"
                  className="h-20 w-full resize-none rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                />
              </div>
            </fieldset>

            {(validationError ?? submitError) && (
              <div
                role="alert"
                aria-live="assertive"
                className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
              >
                <AlertTriangle className="h-4 w-4 shrink-0" />
                {validationError ?? submitError}
              </div>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                aria-busy={submitting}
                className="btn-press flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-current" />}
                Add Knowledge Source
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

const EMPTY_KS: Resource[] = []

export default function KnowledgeSources() {
  const { sources, loading, error, fetchResources, createResource, deleteResource } =
    useResourceStore(
      useShallow((s) => ({
        sources: s.resources['knowledge-sources'] ?? EMPTY_KS,
        loading: s.loading,
        error: s.error,
        fetchResources: s.fetchResources,
        createResource: s.createResource,
        deleteResource: s.deleteResource,
      })),
    )

  const toasts = useToastStore()

  const [addOpen, setAddOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleting, setDeleting] = useState(false)
  const { deleteError, showDeleteError, clearDeleteError } = useDeleteError()

  useDocumentTitle('Knowledge Sources')

  useEffect(() => {
    void fetchResources('knowledge-sources')
  }, [fetchResources])

  const handleAdd = async (form: AddKnowledgeSourceForm) => {
    setSubmitting(true)
    setSubmitError(null)
    try {
      const spec: Record<string, unknown> = { type: form.type }
      if (form.description.trim()) spec.description = form.description.trim()

      if (form.type === 'url') {
        spec.urls = [form.source.trim()]
      } else if (form.type === 'string') {
        spec.content = form.source
      } else {
        spec.file_paths = [form.source.trim()]
      }

      await createResource({
        apiVersion: API_VERSION,
        kind: 'KnowledgeSource',
        metadata: { name: form.name, project: 'default' },
        spec,
      })
      setAddOpen(false)
      toasts.success(`Knowledge source "${form.name}" created`)
    } catch (err) {
      setSubmitError(getErrorMessage(err, 'Failed to create knowledge source'))
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    const name = deleteTarget
    setDeleting(true)
    try {
      await deleteResource('knowledge-sources', name)
      setDeleteTarget(null)
      toasts.success(`Knowledge source "${name}" deleted`)
    } catch (err) {
      setDeleteTarget(null)
      showDeleteError(getErrorMessage(err, 'Failed to delete knowledge source'))
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-6">
          <PageHeader
            title="Knowledge Sources"
            description="RAG knowledge sources for agent memory and context"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => void fetchResources('knowledge-sources')}
                  disabled={loading}
                  className="inline-flex items-center gap-1.5 rounded-md border bg-background px-3 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                  aria-label="Refresh knowledge sources"
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
                  onClick={() => {
                    setSubmitError(null)
                    setAddOpen(true)
                  }}
                  className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-4 w-4" />
                  Add Knowledge Source
                </button>
              </>
            }
          />
        </div>

        {deleteError && (
          <ErrorAlert
            message={deleteError}
            actionLabel="Dismiss"
            onAction={() => clearDeleteError()}
            ariaLabel="Dismiss error"
            className="mb-4"
          />
        )}

        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchResources('knowledge-sources')}
            ariaLabel="Retry loading knowledge sources"
            className="mb-4"
          />
        )}

        {loading && sources.length === 0 ? (
          <KnowledgeCardSkeleton count={6} />
        ) : sources.length === 0 ? (
          <EmptyState
            icon={<BookOpen />}
            title="No knowledge sources configured"
            description="Add knowledge sources to enable RAG for your agents"
            action={{
              label: 'Add Knowledge Source',
              onClick: () => {
                setSubmitError(null)
                setAddOpen(true)
              },
            }}
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {sources.map((resource) => (
              <KnowledgeSourceCard
                key={resource.id}
                resource={resource}
                onDelete={() => setDeleteTarget(resource.metadata.name)}
              />
            ))}
          </div>
        )}
      </div>

      <AddKnowledgeSourceDialog
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
        title="Delete knowledge source"
        description={`Delete "${deleteTarget}"? This cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleDelete()}
        loading={deleting}
      />
    </div>
  )
}
