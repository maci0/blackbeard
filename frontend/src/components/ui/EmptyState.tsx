import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: { label: string; href: string }
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="page-enter flex flex-col items-center justify-center py-16 text-center">
      <div aria-hidden="true" className="mb-4 text-muted-foreground/60 [&>svg]:h-12 [&>svg]:w-12">
        {icon}
      </div>
      <h2 className="text-sm font-medium text-foreground">{title}</h2>
      <p className="mt-1 max-w-xs text-xs text-muted-foreground">{description}</p>
      {action && (
        <Link
          to={action.href}
          className="mt-4 inline-flex items-center rounded-lg bg-primary px-4 py-2 text-xs font-semibold text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {action.label}
        </Link>
      )}
    </div>
  )
}
