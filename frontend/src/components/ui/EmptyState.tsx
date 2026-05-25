import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

interface EmptyStateProps {
  icon: ReactNode
  title: string
  description: string
  action?: { label: string; href?: string; onClick?: () => void }
}

export function EmptyState({ icon, title, description, action }: EmptyStateProps) {
  const actionClass =
    'mt-4 inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring'

  return (
    <div className="page-enter flex flex-col items-center justify-center py-16 text-center">
      <div aria-hidden="true" className="mb-4 text-muted-foreground/60 [&>svg]:h-12 [&>svg]:w-12">
        {icon}
      </div>
      <h2 className="text-base font-medium text-foreground">{title}</h2>
      <p className="mt-1 max-w-xs text-sm text-muted-foreground">{description}</p>
      {action &&
        (action.href ? (
          <Link to={action.href} className={actionClass}>
            {action.label}
          </Link>
        ) : (
          action.onClick && (
            <button type="button" onClick={action.onClick} className={actionClass}>
              {action.label}
            </button>
          )
        ))}
    </div>
  )
}
