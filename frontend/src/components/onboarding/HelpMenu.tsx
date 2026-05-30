import { useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import * as Dialog from '@radix-ui/react-dialog'
import { RotateCcw, BookOpen, Keyboard, X } from 'lucide-react'
import { modKey } from '@/lib/platform'

/* ------------------------------------------------------------------ */
/* Keyboard shortcuts dialog                                           */
/* ------------------------------------------------------------------ */

interface Shortcut {
  keys: string[]
  label: string
}

const SHORTCUTS: Shortcut[] = [
  { keys: [modKey, 'Z'], label: 'Undo' },
  { keys: [modKey, '⇧', 'Z'], label: 'Redo' },
  { keys: ['Del', 'Backspace'], label: 'Delete selected node' },
  { keys: ['Enter', 'Space'], label: 'Add node from palette' },
  { keys: ['Tab'], label: 'Navigate between elements' },
]

function KeyboardShortcutsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[60] bg-black/40 backdrop-blur-sm" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-[60] w-[400px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-border bg-card shadow-2xl focus:outline-none">
          {/* Header */}
          <div className="flex items-center justify-between border-b px-5 py-4">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                Keyboard Shortcuts
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-muted-foreground">
                Studio canvas shortcuts
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="rounded p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Shortcuts list */}
          <div className="space-y-1 p-5">
            {SHORTCUTS.map((s) => (
              <div
                key={s.label}
                className="flex items-center justify-between border-b border-border/50 py-2 last:border-0"
              >
                <span className="text-sm text-muted-foreground">{s.label}</span>
                <div className="flex items-center gap-1">
                  {s.keys.map((k) => (
                    <kbd
                      key={k}
                      className="text-2xs inline-flex h-7 min-w-[1.75rem] items-center justify-center rounded border border-border bg-muted px-1.5 font-mono font-semibold text-foreground shadow-sm"
                    >
                      {k}
                    </kbd>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

/* ------------------------------------------------------------------ */
/* HelpMenu                                                            */
/* ------------------------------------------------------------------ */

interface HelpMenuProps {
  onRestartTour: () => void
}

export default function HelpMenu({ onRestartTour }: HelpMenuProps) {
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  return (
    <>
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            aria-label="Help menu"
            title="Help menu"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-full border border-border text-xs font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            ?
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            sideOffset={8}
            align="start"
            side="top"
            className="bg-popover z-50 min-w-[190px] rounded-lg border border-border py-1 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          >
            <DropdownMenu.Item
              onSelect={onRestartTour}
              className="mx-1 flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
            >
              <RotateCcw className="h-3.5 w-3.5 text-muted-foreground" />
              Restart tour
            </DropdownMenu.Item>

            <DropdownMenu.Item
              onSelect={() =>
                window.open(
                  'https://github.com/blackbeard-ai/blackbeard/blob/main/docs/getting-started.md',
                  '_blank',
                  'noopener,noreferrer',
                )
              }
              className="mx-1 flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
            >
              <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
              Documentation
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="mx-2 my-1 h-px bg-border" />

            <DropdownMenu.Item
              onSelect={() => setShortcutsOpen(true)}
              className="mx-1 flex cursor-pointer items-center gap-2.5 rounded-sm px-3 py-2 text-[13px] font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
            >
              <Keyboard className="h-3.5 w-3.5 text-muted-foreground" />
              Keyboard shortcuts
            </DropdownMenu.Item>
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      <KeyboardShortcutsDialog open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </>
  )
}
