import { useEffect, useState, useCallback } from 'react'
import { FolderOpen, Plus, Trash2, RefreshCw, Search, X, Shield } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { SmartTime } from '@/components/ui/SmartTime'
import { caseFold, cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useToastStore } from '@/stores/toastStore'
import type { Resource } from '@/lib/types'

export default function Projects() {
  useDocumentTitle('Projects')

  const [projects, setProjects] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const toasts = useToastStore()

  const fetchProjects = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const resp = await api.get<{ items: Resource[]; total: number }>('/api/v1/projects')
      setProjects(resp.items)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load projects'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchProjects()
  }, [fetchProjects])

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await api.delete(`/api/v1/projects/${deleteTarget}`)
      toasts.success('Project deleted')
      setDeleteTarget(null)
      void fetchProjects()
    } catch (err) {
      toasts.error(getErrorMessage(err, 'Failed to delete project'))
    }
  }

  const filtered = filter
    ? projects.filter((p) => caseFold(p.metadata.name).includes(caseFold(filter)))
    : projects

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-5xl p-6">
        <PageHeader
          title="Projects"
          description="Manage project scopes, quotas, and guardrails"
          actions={
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => void fetchProjects()}
                disabled={loading}
                aria-label="Refresh"
                className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <RefreshCw
                  className={cn('h-4 w-4', loading && 'animate-spin motion-reduce:animate-none')}
                />
              </button>
              <button
                type="button"
                onClick={() => setCreateOpen(true)}
                className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <Plus className="h-4 w-4" />
                New Project
              </button>
            </div>
          }
        />

        {projects.length > 0 && (
          <div className="mt-6">
            <div className="relative max-w-xs">
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <input
                type="text"
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                placeholder="Filter projects..."
                aria-label="Filter projects"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
        )}

        <div className="mt-6">
          {error && (
            <ErrorAlert
              message={error}
              onAction={() => void fetchProjects()}
              actionLabel="Retry"
              onDismiss={() => setError(null)}
              className="mb-4"
            />
          )}

          {loading ? (
            <TableSkeleton />
          ) : projects.length === 0 ? (
            <EmptyState
              icon={<FolderOpen className="h-10 w-10" />}
              title="No projects yet"
              description="Projects organize resources into logical groups with their own quotas and guardrails."
              action={{ label: 'Create Project', onClick: () => setCreateOpen(true) }}
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Search className="h-10 w-10" />}
              title="No projects match your filter"
              description={`Nothing matched "${filter}". Try a different name or clear the filter.`}
              action={{ label: 'Clear filter', onClick: () => setFilter('') }}
            />
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm" aria-label="Projects">
                <thead>
                  <tr className="border-b bg-muted/30 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th scope="col" className="px-4 py-3">
                      Name
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Description
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Guardrails
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Quota
                    </th>
                    <th scope="col" className="px-4 py-3">
                      Updated
                    </th>
                    <th scope="col" className="px-4 py-3 text-right">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {filtered.map((project) => {
                    // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition -- spec field may be absent
                    const guardrails = (project.spec.guardrails as string[]) ?? []
                    const quota = project.spec.resource_quota as
                      | { max_resources?: number; max_executions_per_hour?: number }
                      | undefined

                    return (
                      <tr
                        key={project.metadata.name}
                        className="transition-colors duration-150 hover:bg-accent/50"
                      >
                        <td className="px-4 py-3">
                          <span className="font-medium">{project.metadata.name}</span>
                          {project.metadata.name === 'default' && (
                            <span className="ml-2 rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                              default
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-muted-foreground">
                          {(project.spec.description as string) || '-'}
                        </td>
                        <td className="px-4 py-3">
                          {guardrails.length > 0 ? (
                            <span className="inline-flex items-center gap-1 text-xs">
                              <Shield className="h-3 w-3 text-emerald-500" />
                              {guardrails.length}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">none</span>
                          )}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          {quota?.max_resources
                            ? `${quota.max_resources} resources`
                            : quota?.max_executions_per_hour
                              ? `${quota.max_executions_per_hour}/hr`
                              : 'unlimited'}
                        </td>
                        <td className="px-4 py-3 text-xs text-muted-foreground">
                          <SmartTime date={project.updated_at} />
                        </td>
                        <td className="px-4 py-3 text-right">
                          {project.metadata.name !== 'default' && (
                            <button
                              type="button"
                              onClick={() => setDeleteTarget(project.metadata.name)}
                              className="flex h-8 w-8 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              aria-label={`Delete project ${project.metadata.name}`}
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <CreateProjectDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={() => void fetchProjects()}
      />

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title="Delete project?"
        description="All resources in this project will become orphaned. This cannot be undone."
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleDelete()}
      />
    </div>
  )
}

function CreateProjectDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated: () => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toasts = useToastStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Project name is required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/api/v1/projects', {
        apiVersion: 'blackbeard/v1',
        kind: 'Project',
        metadata: { name: name.trim().toLowerCase().replace(/\s+/g, '-') },
        spec: { description: description.trim() },
      })
      toasts.success(`Project "${name}" created`)
      setName('')
      setDescription('')
      onOpenChange(false)
      onCreated()
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to create project'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-semibold">New Project</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Projects group resources and apply shared guardrails.
          </Dialog.Description>
          <button
            type="button"
            onClick={() => onOpenChange(false)}
            className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
          {error && (
            <div
              role="alert"
              className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </div>
          )}
          <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-4">
            <div>
              <label htmlFor="proj-name" className="mb-1.5 block text-sm font-medium">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                id="proj-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                aria-required="true"
                autoFocus
                pattern="[a-z0-9][a-z0-9\-]*"
                aria-describedby="proj-name-hint"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="my-project"
              />
              <p id="proj-name-hint" className="mt-1 text-xs text-muted-foreground">
                Lowercase letters, numbers, and hyphens only
              </p>
            </div>
            <div>
              <label htmlFor="proj-desc" className="mb-1.5 block text-sm font-medium">
                Description
              </label>
              <input
                id="proj-desc"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="Production workloads"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={submitting}
                className="btn-press inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-current" />}
                Create
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
