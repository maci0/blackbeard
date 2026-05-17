import { useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Play, AlertCircle, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { modKey } from '@/lib/platform'

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function RunDialog({
  open,
  onOpenChange,
  crewName,
  onRun,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  crewName: string
  onRun: (inputs: string) => void
}) {
  const [inputs, setInputs] = useState('{}')
  const [error, setError] = useState('')

  function handleRun() {
    try {
      JSON.parse(inputs)
      setError('')
      onRun(inputs)
    } catch {
      setError('Invalid JSON — check for missing quotes, commas, or brackets')
    }
  }

  return (
    <Dialog.Root
      open={open}
      onOpenChange={(v) => {
        if (v) setError('')
        onOpenChange(v)
      }}
    >
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-border bg-card p-0 shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-gradient-to-r from-emerald-600 to-emerald-500 px-5 py-4">
            <div>
              <Dialog.Title className="text-sm font-semibold text-white">Run Crew</Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-white/70">
                Kick off <span className="font-bold">{crewName}</span> with optional inputs
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="flex h-11 w-11 items-center justify-center rounded text-white/70 transition-colors hover:bg-white/20 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/50"
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="space-y-4 p-5">
            <div>
              <label
                htmlFor="run-dialog-inputs"
                className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
              >
                Crew Inputs (JSON)
              </label>
              <textarea
                id="run-dialog-inputs"
                autoFocus
                aria-describedby={error ? 'run-dialog-error' : 'run-dialog-hint'}
                aria-invalid={error ? true : undefined}
                className="h-32 w-full resize-none rounded-lg border border-border bg-muted/40 px-3 py-2.5 font-mono text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={inputs}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                  const val = e.target.value
                  setInputs(val)
                  if (val.trim()) {
                    try {
                      JSON.parse(val)
                      setError('')
                    } catch {
                      setError('Invalid JSON — check for missing quotes, commas, or brackets')
                    }
                  } else {
                    setError('')
                  }
                }}
                onKeyDown={(e: KeyboardEvent<HTMLTextAreaElement>) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                    e.preventDefault()
                    handleRun()
                  }
                }}
                placeholder='{ "topic": "AI safety" }'
                spellCheck={false}
                autoComplete="off"
                autoCapitalize="off"
                autoCorrect="off"
              />
              <p id="run-dialog-hint" className="mt-1 text-xs text-muted-foreground/70">
                Press {modKey}+Enter to run
              </p>
              {error && (
                <p
                  id="run-dialog-error"
                  role="alert"
                  className="mt-1 flex items-center gap-1 text-xs text-destructive"
                >
                  <AlertCircle className="h-3 w-3" />
                  {error}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                onClick={handleRun}
                disabled={!!error}
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Play className="h-3.5 w-3.5" />
                Run
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
