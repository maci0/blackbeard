import { LayoutGrid, List } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ViewMode } from '@/stores/viewPrefsStore'

interface ViewToggleProps {
  mode: ViewMode
  onChange: (mode: ViewMode) => void
}

export function ViewToggle({ mode, onChange }: ViewToggleProps) {
  return (
    <div
      className="inline-flex rounded-lg border bg-muted/40 p-0.5"
      role="radiogroup"
      aria-label="View mode"
    >
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'cards'}
        aria-label="Card view"
        title="Card view"
        onClick={() => onChange('cards')}
        className={cn(
          'flex h-9 w-9 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          mode === 'cards'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <LayoutGrid className="h-3.5 w-3.5" />
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'list'}
        aria-label="List view"
        title="List view"
        onClick={() => onChange('list')}
        className={cn(
          'flex h-9 w-9 items-center justify-center rounded-md transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          mode === 'list'
            ? 'bg-background text-foreground shadow-sm'
            : 'text-muted-foreground hover:text-foreground',
        )}
      >
        <List className="h-3.5 w-3.5" />
      </button>
    </div>
  )
}
