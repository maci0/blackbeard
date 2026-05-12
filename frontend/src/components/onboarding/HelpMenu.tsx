import { useState } from 'react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import * as Dialog from '@radix-ui/react-dialog'
import { RotateCcw, BookOpen, Keyboard, X } from 'lucide-react'

/* ------------------------------------------------------------------ */
/* Keyboard shortcuts dialog                                           */
/* ------------------------------------------------------------------ */

interface Shortcut {
  keys: string[]
  label: string
}

const SHORTCUTS: Shortcut[] = [
  { keys: ['⌘', 'Z'], label: 'Undo' },
  { keys: ['⌘', '⇧', 'Z'], label: 'Redo' },
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
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-[60]" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[60] w-[400px] max-w-[90vw] bg-card border border-border rounded-xl shadow-2xl overflow-hidden focus:outline-none">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b">
            <div>
              <Dialog.Title className="text-sm font-semibold text-foreground">
                Keyboard Shortcuts
              </Dialog.Title>
              <Dialog.Description className="text-xs text-muted-foreground mt-0.5">
                Studio canvas shortcuts
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Shortcuts list */}
          <div className="p-5 space-y-1">
            {SHORTCUTS.map((s) => (
              <div
                key={s.label}
                className="flex items-center justify-between py-2 border-b border-border/50 last:border-0"
              >
                <span className="text-sm text-muted-foreground">{s.label}</span>
                <div className="flex items-center gap-1">
                  {s.keys.map((k) => (
                    <kbd
                      key={k}
                      className="inline-flex items-center justify-center min-w-[1.75rem] h-7 px-1.5 text-[11px] font-semibold font-mono bg-muted border border-border rounded shadow-sm text-foreground"
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
            className="w-8 h-8 rounded-full border border-border text-[12px] font-bold text-muted-foreground hover:text-foreground hover:bg-muted transition-colors flex items-center justify-center focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          >
            ?
          </button>
        </DropdownMenu.Trigger>

        <DropdownMenu.Portal>
          <DropdownMenu.Content
            sideOffset={8}
            align="start"
            side="top"
            className="z-50 min-w-[190px] bg-popover border border-border rounded-lg shadow-xl py-1 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95"
          >
            <DropdownMenu.Item
              onSelect={onRestartTour}
              className="flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium cursor-pointer text-foreground hover:bg-muted focus:bg-muted focus:outline-none rounded-sm mx-1 transition-colors"
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
              className="flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium cursor-pointer text-foreground hover:bg-muted focus:bg-muted focus:outline-none rounded-sm mx-1 transition-colors"
            >
              <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
              Documentation
            </DropdownMenu.Item>

            <DropdownMenu.Separator className="h-px bg-border my-1 mx-2" />

            <DropdownMenu.Item
              onSelect={() => setShortcutsOpen(true)}
              className="flex items-center gap-2.5 px-3 py-2 text-[13px] font-medium cursor-pointer text-foreground hover:bg-muted focus:bg-muted focus:outline-none rounded-sm mx-1 transition-colors"
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
