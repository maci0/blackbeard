import { useState, type ChangeEvent } from 'react'
import { Play, AlertCircle, X } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'

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
    } catch (e) {
      const detail = e instanceof SyntaxError ? e.message : 'Unknown error'
      setError(`Invalid JSON: ${detail}`)
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 w-[480px] max-w-[90vw] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-xl border border-border bg-card p-0 shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          {/* Header */}
          <div className="flex items-center justify-between border-b bg-gradient-to-r from-emerald-600 to-emerald-500 px-5 py-4">
            <div>
              <Dialog.Title className="text-sm font-semibold text-white">Run Crew</Dialog.Title>
              <Dialog.Description className="text-2xs mt-0.5 text-white/70">
                Kick off <span className="font-bold">{crewName}</span> with optional inputs
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="rounded p-1 text-white/70 transition-colors hover:bg-white/20 hover:text-white"
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
                className="h-32 w-full resize-none rounded-lg border border-border bg-muted/40 px-3 py-2.5 font-mono text-xs text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                value={inputs}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => {
                  setInputs(e.target.value)
                  if (error) setError('')
                }}
                placeholder='{ "topic": "AI safety" }'
                spellCheck={false}
              />
              {error && (
                <p role="alert" className="text-2xs mt-1 flex items-center gap-1 text-destructive">
                  <AlertCircle className="h-3 w-3" />
                  {error}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button className="rounded-lg border border-border px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                onClick={handleRun}
                className="flex items-center gap-2 rounded-lg bg-emerald-600 px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700"
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
