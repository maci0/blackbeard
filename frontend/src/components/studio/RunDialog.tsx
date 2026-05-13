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
        <Dialog.Overlay className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in data-[state=closed]:fade-out" />
        <Dialog.Content className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-50 w-[480px] max-w-[90vw] bg-card border border-border rounded-xl shadow-2xl p-0 overflow-hidden data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95">
          {/* Header */}
          <div className="flex items-center justify-between px-5 py-4 border-b bg-gradient-to-r from-emerald-600 to-emerald-500">
            <div>
              <Dialog.Title className="text-sm font-semibold text-white">
                Run Crew
              </Dialog.Title>
              <Dialog.Description className="text-[11px] text-white/70 mt-0.5">
                Kick off <span className="font-bold">{crewName}</span> with optional inputs
              </Dialog.Description>
            </div>
            <Dialog.Close
              className="p-1 rounded text-white/70 hover:text-white hover:bg-white/20 transition-colors"
              aria-label="Close"
            >
              <X className="w-4 h-4" />
            </Dialog.Close>
          </div>

          {/* Body */}
          <div className="p-5 space-y-4">
            <div>
              <label
                htmlFor="run-dialog-inputs"
                className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1.5"
              >
                Crew Inputs (JSON)
              </label>
              <textarea
                id="run-dialog-inputs"
                className="w-full font-mono text-[12px] bg-muted/40 border border-border rounded-lg px-3 py-2.5 h-32 resize-none focus:outline-none focus:ring-2 focus:ring-ring text-foreground"
                value={inputs}
                onChange={(e: ChangeEvent<HTMLTextAreaElement>) => { setInputs(e.target.value); if (error) setError('') }}
                placeholder='{ "topic": "AI safety" }'
                spellCheck={false}
              />
              {error && (
                <p role="alert" className="mt-1 text-[11px] text-destructive flex items-center gap-1">
                  <AlertCircle className="w-3 h-3" />
                  {error}
                </p>
              )}
            </div>

            <div className="flex justify-end gap-2">
              <Dialog.Close asChild>
                <button className="px-4 py-2 text-[12px] font-medium text-muted-foreground border border-border rounded-lg hover:bg-muted transition-colors">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                onClick={handleRun}
                className="flex items-center gap-2 px-4 py-2 text-[12px] font-semibold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 transition-colors shadow-sm"
              >
                <Play className="w-3.5 h-3.5" />
                Run
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
