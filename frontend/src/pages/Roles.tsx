import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import {
  Shield,
  Search,
  RefreshCw,
  Plus,
  X,
  Users as UsersIcon,
  ListChecks,
  Trash2,
} from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { RuleBuilder, type Rule } from '@/components/rbac/RuleBuilder'
import { caseFold, cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks/useDocumentTitle'
import { useToastStore } from '@/stores/toastStore'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface RoleRecord {
  id: string
  name: string
  description: string
  rules: Rule[]
  bound_subjects: number
  created_at: string
}

/* ------------------------------------------------------------------ */
/* Role card                                                           */
/* ------------------------------------------------------------------ */

function RoleCard({
  role,
  selected,
  onSelect,
}: {
  role: RoleRecord
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onSelect()
        }
      }}
      aria-label={`Role: ${role.name}, press Enter to view details`}
      aria-pressed={selected}
      className={cn(
        'flex w-full flex-col overflow-hidden rounded-lg border bg-card text-left shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        selected && 'ring-2 ring-primary',
      )}
    >
      {/* Header */}
      <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2">
            <div className="shrink-0 rounded-md border border-purple-200 bg-purple-100 p-1.5 dark:border-purple-800 dark:bg-purple-900">
              <Shield className="h-4 w-4 text-purple-600 dark:text-purple-400" />
            </div>
            <p className="truncate text-sm font-semibold" title={role.name}>
              {role.name}
            </p>
          </div>
        </div>
      </div>

      {/* Body */}
      <div className="flex flex-1 flex-col gap-2 px-4 py-3">
        {role.description && (
          <p className="line-clamp-2 text-sm leading-relaxed text-muted-foreground">
            {role.description}
          </p>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between border-t bg-muted/10 px-4 py-2.5">
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <ListChecks className="h-3 w-3" aria-hidden="true" />
          {role.rules.length} rule{role.rules.length !== 1 ? 's' : ''}
        </span>
        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
          <UsersIcon className="h-3 w-3" aria-hidden="true" />
          {role.bound_subjects} {role.bound_subjects === 1 ? 'user' : 'users'}
        </span>
      </div>
    </button>
  )
}

/* ------------------------------------------------------------------ */
/* Role detail                                                         */
/* ------------------------------------------------------------------ */

function RoleDetail({
  role,
  onClose,
  onDeleted,
}: {
  role: RoleRecord
  onClose: () => void
  onDeleted: () => void
}) {
  const [deleteOpen, setDeleteOpen] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const toasts = useToastStore()

  const handleDelete = async () => {
    setDeleting(true)
    try {
      await api.delete(`/api/v1/roles/${role.name}`)
      toasts.success(`Role "${role.name}" deleted`)
      setDeleteOpen(false)
      onDeleted()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to delete role')
      toasts.error(message)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">{role.name}</h2>
          {role.description && (
            <p className="mt-0.5 text-sm text-muted-foreground">{role.description}</p>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setDeleteOpen(true)}
            aria-label={`Delete role ${role.name}`}
            className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Trash2 className="h-4 w-4" />
          </button>
          <button
            onClick={onClose}
            aria-label="Close role details"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      <h3 className="mb-2 text-sm font-semibold">Rules</h3>
      {role.rules.length === 0 ? (
        <p className="text-sm text-muted-foreground">No rules defined.</p>
      ) : (
        <div className="space-y-3">
          {role.rules.map((rule, idx) => (
            <div key={idx} className="rounded-md border bg-muted/20 p-3 text-sm">
              <div className="mb-1 flex flex-wrap gap-1">
                <span className="text-xs font-medium text-muted-foreground">Resources:</span>
                {rule.resources.map((r) => (
                  <span
                    key={r}
                    className="inline-flex rounded bg-blue-100 px-1.5 py-0.5 text-xs font-medium text-blue-800 dark:bg-blue-900 dark:text-blue-200"
                  >
                    {r}
                  </span>
                ))}
              </div>
              <div className="flex flex-wrap gap-1">
                <span className="text-xs font-medium text-muted-foreground">Verbs:</span>
                {rule.verbs.map((v) => (
                  <span
                    key={v}
                    className="inline-flex rounded bg-emerald-100 px-1.5 py-0.5 text-xs font-medium text-emerald-800 dark:bg-emerald-900 dark:text-emerald-200"
                  >
                    {v}
                  </span>
                ))}
              </div>
              {rule.resourceNames && rule.resourceNames.length > 0 && (
                <div className="mt-1 flex flex-wrap gap-1">
                  <span className="text-xs font-medium text-muted-foreground">Names:</span>
                  {rule.resourceNames.map((n) => (
                    <span
                      key={n}
                      className="inline-flex rounded bg-gray-100 px-1.5 py-0.5 text-xs font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-200"
                    >
                      {n}
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <ConfirmDialog
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
        title="Delete role"
        description={`Are you sure you want to delete the role "${role.name}"?${role.bound_subjects > 0 ? ` ${role.bound_subjects} ${role.bound_subjects === 1 ? 'user is' : 'users are'} currently assigned this role.` : ''} This action cannot be undone.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => void handleDelete()}
        loading={deleting}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Create role dialog                                                  */
/* ------------------------------------------------------------------ */

function CreateRoleDialog({
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
  const [rules, setRules] = useState<Rule[]>([{ resources: [], verbs: [], resourceNames: [] }])
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toasts = useToastStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) {
      setError('Role name is required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      const validRules = rules.filter((r) => r.resources.length > 0 && r.verbs.length > 0)
      await api.post('/api/v1/roles', {
        apiVersion: 'blackbeard/v1',
        kind: 'Role',
        metadata: { name: name.toLowerCase().replace(/\s+/g, '-') },
        spec: { description, rules: validRules },
      })
      toasts.success(`Role "${name}" created`)
      setName('')
      setDescription('')
      setRules([{ resources: [], verbs: [], resourceNames: [] }])
      onOpenChange(false)
      onCreated()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to create role')
      setError(message)
      toasts.error(message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 max-h-[85vh] w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-semibold">Create Role</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Define a role with permissions for platform resources.
          </Dialog.Description>

          {error && (
            <div
              role="alert"
              aria-live="assertive"
              className="mt-3 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            >
              {error}
            </div>
          )}

          <form onSubmit={(e) => void handleSubmit(e)} className="mt-4 space-y-4">
            <div>
              <label htmlFor="role-name" className="mb-1.5 block text-sm font-medium">
                Name <span className="text-destructive">*</span>
              </label>
              <input
                id="role-name"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                aria-required="true"
                autoFocus
                autoComplete="off"
                spellCheck={false}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="e.g. crew-manager"
              />
            </div>

            <div>
              <label htmlFor="role-description" className="mb-1.5 block text-sm font-medium">
                Description
              </label>
              <input
                id="role-description"
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="What does this role allow?"
              />
            </div>

            <div>
              <p className="mb-2 text-sm font-medium">Rules</p>
              <RuleBuilder rules={rules} onChange={setRules} />
            </div>

            <div className="flex justify-end gap-3 pt-2">
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
                {submitting && <Spinner size="sm" className="text-current" />}
                Create Role
              </button>
            </div>
          </form>

          <Dialog.Close asChild>
            <button
              type="button"
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Roles() {
  const [roles, setRoles] = useState<RoleRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [createOpen, setCreateOpen] = useState(false)
  const [selectedRole, setSelectedRole] = useState<RoleRecord | null>(null)
  const detailPanelRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useDocumentTitle('Roles')

  useEffect(() => {
    if (selectedRole) {
      requestAnimationFrame(() => {
        detailPanelRef.current?.focus()
        detailPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })
    }
  }, [selectedRole])

  const fetchRoles = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<{
        items: Array<{
          id: string
          metadata: { name: string }
          spec: { description?: string; rules?: Rule[] }
          created_at: string
        }>
        total: number
      }>('/api/v1/roles')
      setRoles(
        result.items.map((r) => ({
          id: r.id,
          name: r.metadata.name,
          description: r.spec.description ?? '',
          rules: r.spec.rules ?? [],
          bound_subjects: 0,
          created_at: r.created_at,
        })),
      )
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load roles'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchRoles()
  }, [fetchRoles])

  const filtered = useMemo(() => {
    if (!search.trim()) return roles
    const q = caseFold(search)
    return roles.filter((r) => caseFold(r.name).includes(q) || caseFold(r.description).includes(q))
  }, [roles, search])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Roles"
            description="Access control roles and permissions"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => void fetchRoles()}
                  disabled={loading}
                  aria-label="Refresh roles"
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
                  onClick={() => setCreateOpen(true)}
                  className="btn-press inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <Plus className="h-4 w-4" />
                  Create Role
                </button>
              </>
            }
          />
        </div>

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchRoles()}
            ariaLabel="Retry loading roles"
            className="mb-4"
          />
        )}

        {/* Search */}
        {roles.length > 0 && (
          <div className="mb-5 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <label htmlFor="roles-search" className="sr-only">
                Search roles
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                ref={searchRef}
                id="roles-search"
                type="search"
                placeholder="Search roles…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            {search && (
              <>
                <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
                  {filtered.length} of {roles.length} roles
                </span>
                <button
                  onClick={() => {
                    setSearch('')
                    searchRef.current?.focus()
                  }}
                  aria-label="Clear search"
                  className="inline-flex min-h-[44px] items-center gap-1 rounded-md px-2 text-sm text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <X className="h-3.5 w-3.5" />
                  Clear search
                </button>
              </>
            )}
          </div>
        )}

        {/* Selected role detail */}
        {selectedRole && (
          <div ref={detailPanelRef} tabIndex={-1} className="mb-4 focus-visible:outline-none">
            <RoleDetail
              role={selectedRole}
              onClose={() => setSelectedRole(null)}
              onDeleted={() => {
                setSelectedRole(null)
                void fetchRoles()
              }}
            />
          </div>
        )}

        {/* Content */}
        {loading && roles.length === 0 ? (
          <TableSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<Shield />}
            title={search ? 'No roles match your search' : 'No roles found'}
            description={
              search ? 'Try a different search term' : 'Create roles to manage access control'
            }
            action={
              !search ? { label: 'Create Role', onClick: () => setCreateOpen(true) } : undefined
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((role) => (
              <RoleCard
                key={role.id}
                role={role}
                selected={selectedRole?.id === role.id}
                onSelect={() => setSelectedRole(role)}
              />
            ))}
          </div>
        )}

        {/* Create role dialog */}
        <CreateRoleDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={() => void fetchRoles()}
        />
      </div>
    </div>
  )
}
