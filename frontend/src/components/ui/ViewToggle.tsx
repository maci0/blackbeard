import { type KeyboardEvent } from 'react'
import { LayoutGrid, List } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { ViewMode } from '@/stores/viewPrefsStore'

interface ViewToggleProps {
  mode: ViewMode
  onChange: (mode: ViewMode) => void
}

const MODES: ViewMode[] = ['cards', 'list']

export function ViewToggle({ mode, onChange }: ViewToggleProps) {
  function handleKeyDown(e: KeyboardEvent) {
    const idx = MODES.indexOf(mode)
    if (idx < 0) return
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault()
      onChange(MODES[(idx + 1) % MODES.length]!)
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault()
      onChange(MODES[(idx - 1 + MODES.length) % MODES.length]!)
    }
  }

  return (
    <div
      className="inline-flex rounded-lg border bg-muted/40 p-0.5"
      role="radiogroup"
      aria-label="View mode"
      onKeyDown={handleKeyDown}
    >
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'cards'}
        aria-label="Card view"
        title="Card view"
        tabIndex={mode === 'cards' ? 0 : -1}
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
        tabIndex={mode === 'list' ? 0 : -1}
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
