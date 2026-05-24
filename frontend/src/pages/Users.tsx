import { useEffect, useState, useMemo, useCallback, useRef } from 'react'
import {
  Users as UsersIcon,
  Search,
  RefreshCw,
  UserPlus,
  ChevronRight,
  X,
  UserMinus,
} from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { Spinner } from '@/components/ui/Spinner'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { cn, getErrorMessage } from '@/lib/utils'
import { formatDate } from '@/lib/formatters'
import { useDocumentTitle } from '@/hooks'
import { useToastStore } from '@/stores/toastStore'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface UserRecord {
  id: string
  email: string
  display_name: string
  is_active: boolean
  role: string
  last_login: string | null
  created_at: string
}

const ROLE_OPTIONS = ['admin', 'editor', 'viewer'] as const

/* ------------------------------------------------------------------ */
/* Status badge                                                        */
/* ------------------------------------------------------------------ */

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold',
        active
          ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
          : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400',
      )}
    >
      <span
        className={cn('h-1.5 w-1.5 rounded-full', active ? 'bg-green-500' : 'bg-gray-400')}
        aria-hidden="true"
      />
      {active ? 'Active' : 'Inactive'}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Role badge                                                          */
/* ------------------------------------------------------------------ */

const ROLE_CLASSES: Record<string, string> = {
  admin:
    'bg-purple-100 text-purple-700 border-purple-200 dark:bg-purple-900 dark:text-purple-300 dark:border-purple-800',
  editor:
    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300 dark:border-blue-800',
  viewer:
    'bg-gray-100 text-gray-600 border-gray-200 dark:bg-gray-800 dark:text-gray-300 dark:border-gray-700',
}

function RoleBadge({ role }: { role: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium capitalize',
        ROLE_CLASSES[role] ??
          'border-gray-200 bg-gray-100 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300',
      )}
    >
      {role}
    </span>
  )
}

/* ------------------------------------------------------------------ */
/* Invite dialog                                                       */
/* ------------------------------------------------------------------ */

function InviteDialog({
  open,
  onOpenChange,
  onInvited,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  onInvited: () => void
}) {
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<string>('viewer')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const toasts = useToastStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email.trim()) {
      setError('Email address is required.')
      return
    }
    setSubmitting(true)
    setError(null)
    try {
      await api.post('/api/v1/users/invite', { email, role })
      toasts.success(`Invitation sent to ${email}`)
      setEmail('')
      setRole('viewer')
      onOpenChange(false)
      onInvited()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to invite user')
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
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-lg font-semibold">Invite User</Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Send an invitation to join the platform.
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
              <label htmlFor="invite-email" className="mb-1.5 block text-sm font-medium">
                Email address <span className="text-destructive">*</span>
              </label>
              <input
                id="invite-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoFocus
                autoComplete="email"
                className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="user@example.com"
              />
            </div>

            <div>
              <label htmlFor="invite-role" className="mb-1.5 block text-sm font-medium">
                Role
              </label>
              <select
                id="invite-role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                {ROLE_OPTIONS.map((r) => (
                  <option key={r} value={r} className="capitalize">
                    {r}
                  </option>
                ))}
              </select>
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
                className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                {submitting && <Spinner size="sm" className="text-current" />}
                Send Invite
              </button>
            </div>
          </form>

          <Dialog.Close asChild>
            <button
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
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
/* User detail panel                                                   */
/* ------------------------------------------------------------------ */

function UserDetailPanel({
  user,
  onClose,
  onUpdated,
}: {
  user: UserRecord
  onClose: () => void
  onUpdated: () => void
}) {
  const [role, setRole] = useState(user.role)
  const [saving, setSaving] = useState(false)
  const [roleStatus, setRoleStatus] = useState<'idle' | 'saved' | 'error'>('idle')
  const [deactivateOpen, setDeactivateOpen] = useState(false)
  const [deactivating, setDeactivating] = useState(false)
  const toasts = useToastStore()

  const handleRoleChange = async (newRole: string) => {
    setRole(newRole)
    setSaving(true)
    setRoleStatus('idle')
    try {
      await api.patch(`/api/v1/users/${user.id}`, { role: newRole })
      setRoleStatus('saved')
      onUpdated()
    } catch {
      setRole(user.role)
      setRoleStatus('error')
    } finally {
      setSaving(false)
    }
  }

  const handleDeactivate = async () => {
    setDeactivating(true)
    try {
      await api.patch(`/api/v1/users/${user.id}`, { is_active: false })
      toasts.success(`User ${user.display_name || user.email} deactivated`)
      setDeactivateOpen(false)
      onUpdated()
    } catch (err) {
      const message = getErrorMessage(err, 'Failed to deactivate user')
      toasts.error(message)
    } finally {
      setDeactivating(false)
    }
  }

  return (
    <div className="rounded-lg border bg-card p-5">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">{user.display_name || user.email}</h2>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close user details"
          title="Close user details"
          className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <dl className="space-y-3 text-sm">
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Email</dt>
          <dd>{user.email}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Status</dt>
          <dd>
            <ActiveBadge active={user.is_active} />
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="text-muted-foreground">Role</dt>
          <dd className="flex items-center gap-2">
            <label htmlFor="user-detail-role" className="sr-only">
              Change role for {user.display_name}
            </label>
            <select
              id="user-detail-role"
              value={role}
              onChange={(e) => void handleRoleChange(e.target.value)}
              disabled={saving}
              className="rounded-md border bg-background px-2 py-1 text-sm capitalize focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            >
              {ROLE_OPTIONS.map((r) => (
                <option key={r} value={r} className="capitalize">
                  {r}
                </option>
              ))}
            </select>
            {saving && <Spinner size="sm" />}
            {roleStatus === 'saved' && (
              <span role="status" className="text-xs text-green-600 dark:text-green-400">
                Saved
              </span>
            )}
            {roleStatus === 'error' && (
              <span role="alert" className="text-xs text-destructive">
                Failed
              </span>
            )}
          </dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Last login</dt>
          <dd>{user.last_login ? formatDate(user.last_login) : 'Never'}</dd>
        </div>
        <div className="flex justify-between">
          <dt className="text-muted-foreground">Created</dt>
          <dd>{formatDate(user.created_at)}</dd>
        </div>
      </dl>

      {user.is_active && (
        <div className="mt-4 border-t pt-4">
          <button
            type="button"
            onClick={() => setDeactivateOpen(true)}
            className="inline-flex items-center gap-1.5 rounded-md border border-destructive/30 px-3 py-2 text-sm text-destructive transition-colors hover:bg-destructive/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <UserMinus className="h-3.5 w-3.5" />
            Deactivate User
          </button>
        </div>
      )}

      <ConfirmDialog
        open={deactivateOpen}
        onOpenChange={setDeactivateOpen}
        title="Deactivate user"
        description={`Are you sure you want to deactivate "${user.display_name || user.email}"? They will lose access to the platform.`}
        confirmLabel="Deactivate"
        confirmVariant="destructive"
        onConfirm={() => void handleDeactivate()}
        loading={deactivating}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Users() {
  const [users, setUsers] = useState<UserRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [search, setSearch] = useState('')
  const [inviteOpen, setInviteOpen] = useState(false)
  const [selectedUser, setSelectedUser] = useState<UserRecord | null>(null)
  const detailPanelRef = useRef<HTMLDivElement>(null)
  const searchRef = useRef<HTMLInputElement>(null)

  useDocumentTitle('Users')

  useEffect(() => {
    if (selectedUser) {
      requestAnimationFrame(() => {
        detailPanelRef.current?.focus()
        detailPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })
    }
  }, [selectedUser])

  const fetchUsers = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<{ items: UserRecord[]; total: number }>('/api/v1/users')
      setUsers(result.items)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load users'))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchUsers()
  }, [fetchUsers])

  const filtered = useMemo(() => {
    if (!search.trim()) return users
    const q = search.toLowerCase()
    return users.filter(
      (u) =>
        u.email.toLowerCase().includes(q) ||
        u.display_name.toLowerCase().includes(q) ||
        u.role.toLowerCase().includes(q),
    )
  }, [users, search])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        {/* Header */}
        <div className="mb-6">
          <PageHeader
            title="Users"
            description="Manage platform users and access"
            actions={
              <>
                <button
                  type="button"
                  onClick={() => void fetchUsers()}
                  aria-label="Refresh users"
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
                  onClick={() => setInviteOpen(true)}
                  className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  <UserPlus className="h-4 w-4" />
                  Invite User
                </button>
              </>
            }
          />
        </div>

        {/* Error */}
        {error && (
          <ErrorAlert
            message={error}
            onAction={() => void fetchUsers()}
            ariaLabel="Retry loading users"
            className="mb-4"
          />
        )}

        {/* Search */}
        {users.length > 0 && (
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <div className="relative min-w-[200px] max-w-sm flex-1">
              <label htmlFor="users-search" className="sr-only">
                Search users
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                ref={searchRef}
                id="users-search"
                type="search"
                placeholder="Search by name or email…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            {search && (
              <>
                <span role="status" aria-live="polite" className="text-sm text-muted-foreground">
                  {filtered.length} of {users.length} users
                </span>
                <button
                  type="button"
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

        {/* Selected user detail */}
        {selectedUser && (
          <div ref={detailPanelRef} tabIndex={-1} className="mb-4 focus-visible:outline-none">
            <UserDetailPanel
              user={selectedUser}
              onClose={() => setSelectedUser(null)}
              onUpdated={() => void fetchUsers()}
            />
          </div>
        )}

        {/* Table */}
        {loading && users.length === 0 ? (
          <TableSkeleton />
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={<UsersIcon />}
            title={search ? 'No users match your search' : 'No users yet'}
            description={search ? 'Try a different search term' : 'Invite users to get started'}
          />
        ) : (
          <div className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="max-h-[calc(100vh-16rem)] overflow-auto">
              <table className="w-full min-w-[640px] text-sm" aria-label="Users">
                <thead className="sticky top-0 z-10">
                  <tr className="border-b bg-muted/60">
                    {(
                      ['Email', 'Display Name', 'Role', 'Status', 'Last Login', 'Created'] as const
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
                  {filtered.map((user) => (
                    <tr
                      key={user.id}
                      onClick={() => setSelectedUser(user)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault()
                          setSelectedUser(user)
                        }
                      }}
                      tabIndex={0}
                      role="row"
                      aria-label={`${user.email} — press Enter to view details`}
                      className={cn(
                        'group cursor-pointer transition-colors duration-150 hover:bg-muted/50 focus-visible:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring',
                        selectedUser?.id === user.id && 'bg-muted/60',
                      )}
                    >
                      <td className="px-4 py-3 font-medium">{user.email}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {user.display_name || (
                          <>
                            <span aria-hidden="true" className="text-muted-foreground/40">
                              —
                            </span>
                            <span className="sr-only">No display name</span>
                          </>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <RoleBadge role={user.role} />
                      </td>
                      <td className="px-4 py-3">
                        <ActiveBadge active={user.is_active} />
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {user.last_login ? formatDate(user.last_login) : 'Never'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {formatDate(user.created_at)}
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
        )}

        {/* Invite dialog */}
        <InviteDialog
          open={inviteOpen}
          onOpenChange={setInviteOpen}
          onInvited={() => void fetchUsers()}
        />
      </div>
    </div>
  )
}
