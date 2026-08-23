import { cn } from '@/lib/utils'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('animate-pulse rounded-md bg-muted/60 motion-reduce:animate-none', className)}
    />
  )
}

export function TableSkeleton() {
  return (
    <div role="status" aria-label="Loading content">
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4">
            <Skeleton className="h-4 w-1/4" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-1/6" />
            <Skeleton className="h-4 w-1/6" />
          </div>
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function CardSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading content">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="overflow-hidden rounded-lg border bg-card">
            <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
              <div className="flex items-center gap-2">
                <Skeleton className="h-8 w-8 rounded-md" />
                <Skeleton className="h-4 w-32" />
              </div>
            </div>
            <div className="space-y-2 px-4 py-3">
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </div>
            <div className="border-t bg-muted/10 px-4 py-3">
              <Skeleton className="h-8 w-full rounded-md" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function ModelSelectorSkeleton() {
  return (
    <div role="status" aria-label="Loading models">
      <Skeleton className="h-9 w-full rounded-md" />
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function DetailSkeleton() {
  return (
    <div role="status" aria-label="Loading details">
      <div className="mx-auto max-w-4xl p-6">
        {/* Breadcrumb */}
        <Skeleton className="mb-5 h-4 w-48" />
        {/* Title + badges */}
        <div className="mb-6 flex items-center gap-3">
          <Skeleton className="h-5 w-16 rounded-full" />
          <Skeleton className="h-7 w-56" />
        </div>
        {/* Info grid */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="rounded-lg border bg-card p-4">
              <Skeleton className="mb-2 h-3 w-16" />
              <Skeleton className="h-5 w-24" />
            </div>
          ))}
        </div>
        {/* Content */}
        <div className="space-y-3 rounded-lg border bg-card p-4 shadow-sm">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="flex items-center gap-4">
              <Skeleton className="h-4 w-1/4" />
              <Skeleton className="h-4 w-1/3" />
              <Skeleton className="h-4 w-1/6" />
            </div>
          ))}
        </div>
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  )
}

export function KnowledgeCardSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div role="status" aria-label="Loading knowledge sources">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: count }).map((_, i) => (
          <div key={i} className="overflow-hidden rounded-lg border bg-card shadow-sm">
            <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
              <div className="flex items-center gap-2">
                <Skeleton className="h-7 w-7 rounded-md" />
                <Skeleton className="h-4 w-28" />
              </div>
            </div>
            <div className="space-y-2.5 px-4 py-3">
              <div className="flex items-center justify-between">
                <Skeleton className="h-3 w-10" />
                <Skeleton className="h-5 w-12 rounded-full" />
              </div>
              <Skeleton className="h-3 w-full" />
              <Skeleton className="h-3 w-3/4" />
            </div>
            <div className="flex items-center justify-between border-t bg-muted/10 px-4 py-2.5">
              <Skeleton className="h-3 w-20" />
              <Skeleton className="h-3 w-6" />
            </div>
          </div>
        ))}
      </div>
      <span className="sr-only">Loading…</span>
    </div>
  )
}
