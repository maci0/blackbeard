import { useEffect } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { isMac, modKey } from '@/lib/platform'

const shiftKey = isMac ? '⇧' : 'Shift'
const deleteKey = isMac ? '⌫' : 'Delete'

const SHORTCUTS = [
  { keys: [modKey, 'S'], description: 'Save crew' },
  { keys: [modKey, 'Z'], description: 'Undo' },
  { keys: [modKey, shiftKey, 'Z'], description: 'Redo' },
  { keys: [deleteKey], description: 'Delete selected node' },
  { keys: ['Double-click'], description: 'Fit view (on empty area)' },
  { keys: [modKey, '/'], description: 'Show this help' },
]

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="inline-flex h-6 min-w-[24px] items-center justify-center rounded border border-border bg-muted px-1.5 text-[11px] font-semibold text-muted-foreground shadow-sm">
      {children}
    </kbd>
  )
}

export function KeyboardShortcuts({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === '/' || e.key === 'k')) {
        e.preventDefault()
        onOpenChange(true)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onOpenChange])

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          <Dialog.Title className="text-base font-semibold">Keyboard Shortcuts</Dialog.Title>
          <Dialog.Description className="sr-only">
            List of keyboard shortcuts available in the studio
          </Dialog.Description>
          <ul className="mt-4 space-y-3">
            {SHORTCUTS.map((shortcut) => (
              <li key={shortcut.description} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{shortcut.description}</span>
                <span className="flex items-center gap-1">
                  {shortcut.keys.map((key, i) => (
                    <Kbd key={i}>{key}</Kbd>
                  ))}
                </span>
              </li>
            ))}
          </ul>
          <Dialog.Close asChild>
            <button
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
