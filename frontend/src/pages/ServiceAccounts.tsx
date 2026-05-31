import { useEffect, useMemo } from 'react'
import { Link } from 'react-router-dom'
import { UserCog, RefreshCw } from 'lucide-react'
import { useResourceStore } from '@/stores/resourceStore'
import { PageHeader } from '@/components/ui/PageHeader'
import { EmptyState } from '@/components/ui/EmptyState'
import { TableSkeleton } from '@/components/ui/Skeleton'
import { SmartTime } from '@/components/ui/SmartTime'
import { cn } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks'

export default function ServiceAccounts() {
  useDocumentTitle('Service Accounts')

  const rawResources = useResourceStore((s) => s.resources['service-accounts'])
  const resources = useMemo(() => rawResources ?? [], [rawResources])
  const loading = useResourceStore((s) => s.loadingKinds['service-accounts'] ?? false)
  const fetchResources = useResourceStore((s) => s.fetchResources)

  useEffect(() => {
    void fetchResources('service-accounts')
  }, [fetchResources])

  const sorted = useMemo(
    () => [...resources].sort((a, b) => a.metadata.name.localeCompare(b.metadata.name)),
    [resources],
  )

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-5xl p-6">
        <PageHeader
          title="Service Accounts"
          description="Machine identities for CI/CD, automations, and agent execution"
          actions={
            <button
              type="button"
              onClick={() => void fetchResources('service-accounts')}
              disabled={loading}
              aria-label="Refresh"
              className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </button>
          }
        />

        <div className="mt-6">
          {loading ? (
            <TableSkeleton />
          ) : resources.length === 0 ? (
            <EmptyState
              icon={<UserCog className="h-10 w-10" />}
              title="No service accounts"
              description="Service accounts are created automatically when agents run. You can also create them manually via the API or YAML."
            />
          ) : (
            <div className="overflow-hidden rounded-lg border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/30 text-left text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    <th className="px-4 py-3">Name</th>
                    <th className="px-4 py-3">Project</th>
                    <th className="px-4 py-3">Description</th>
                    <th className="px-4 py-3">Version</th>
                    <th className="px-4 py-3">Updated</th>
                  </tr>
                </thead>
                <tbody className="divide-y">
                  {sorted.map((sa) => (
                    <tr
                      key={sa.metadata.name}
                      className="transition-colors duration-150 hover:bg-accent/50"
                    >
                      <td className="px-4 py-3">
                        <Link
                          to={`/resources/service-accounts/${sa.metadata.name}`}
                          className="font-medium text-primary hover:underline"
                        >
                          {sa.metadata.name}
                        </Link>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{sa.metadata.project}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {(sa.spec.description as string) || '-'}
                      </td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">v{sa.version}</td>
                      <td className="px-4 py-3 text-xs text-muted-foreground">
                        <SmartTime date={sa.updated_at} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
