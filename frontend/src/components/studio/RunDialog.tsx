import { useState, type ChangeEvent, type KeyboardEvent } from 'react'
import { Play, AlertCircle, X, Loader2, GraduationCap, FlaskConical } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { modKey } from '@/lib/platform'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export type RunMode = 'run' | 'train' | 'test'

export interface RunParams {
  mode: RunMode
  inputs: string
  iterations: number
  filename: string
}

/* ------------------------------------------------------------------ */
/* Mode config                                                         */
/* ------------------------------------------------------------------ */

const MODE_CONFIG: Record<
  RunMode,
  { label: string; icon: typeof Play; gradient: string; verb: string; verbLoading: string }
> = {
  run: {
    label: 'Run',
    icon: Play,
    gradient: 'from-emerald-600 to-emerald-500',
    verb: 'Run',
    verbLoading: 'Starting…',
  },
  train: {
    label: 'Train',
    icon: GraduationCap,
    gradient: 'from-violet-600 to-violet-500',
    verb: 'Train',
    verbLoading: 'Starting…',
  },
  test: {
    label: 'Test',
    icon: FlaskConical,
    gradient: 'from-blue-600 to-blue-500',
    verb: 'Test',
    verbLoading: 'Starting…',
  },
}

const BUTTON_COLORS: Record<RunMode, string> = {
  run: 'bg-emerald-600 hover:bg-emerald-700 dark:bg-emerald-500 dark:hover:bg-emerald-600',
  train: 'bg-violet-600 hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-600',
  test: 'bg-blue-600 hover:bg-blue-700 dark:bg-blue-500 dark:hover:bg-blue-600',
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function RunDialog({
  open,
  onOpenChange,
  crewName,
  onRun,
  loading = false,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  crewName: string
  onRun: (params: RunParams) => void
  loading?: boolean
}) {
  const [mode, setMode] = useState<RunMode>('run')
  const [inputs, setInputs] = useState('{}')
  const [error, setError] = useState('')
  const [iterations, setIterations] = useState(3)
  const [filename, setFilename] = useState('training_data.pkl')

  const config = MODE_CONFIG[mode]
  const Icon = config.icon

  function handleRun() {
    try {
      JSON.parse(inputs)
      setError('')
      onRun({ mode, inputs, iterations, filename })
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
          <div
            className={`flex items-center justify-between border-b bg-gradient-to-r ${config.gradient} px-5 py-4`}
          >
            <div>
              <Dialog.Title className="text-sm font-semibold text-white">
                {config.verb} Crew
              </Dialog.Title>
              <Dialog.Description className="mt-0.5 text-xs text-white/70">
                {mode === 'run' && (
                  <>
                    Kick off <span className="font-bold">{crewName}</span> with optional inputs
                  </>
                )}
                {mode === 'train' && (
                  <>
                    Train <span className="font-bold">{crewName}</span> over multiple iterations
                  </>
                )}
                {mode === 'test' && (
                  <>
                    Test <span className="font-bold">{crewName}</span> over multiple iterations
                  </>
                )}
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
            {/* Mode selector */}
            <fieldset>
              <legend className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                Mode
              </legend>
              <div
                className="inline-flex rounded-lg border border-border bg-muted/40 p-0.5"
                role="radiogroup"
                aria-label="Execution mode"
              >
                {(['run', 'train', 'test'] as const).map((m) => {
                  const mc = MODE_CONFIG[m]
                  const MIcon = mc.icon
                  return (
                    <button
                      key={m}
                      role="radio"
                      aria-checked={mode === m}
                      onClick={() => setMode(m)}
                      className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                        mode === m
                          ? 'bg-background text-foreground shadow-sm'
                          : 'text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      <MIcon className="h-3 w-3" aria-hidden="true" />
                      {mc.label}
                    </button>
                  )
                })}
              </div>
            </fieldset>

            {/* Iterations (train/test only) */}
            {(mode === 'train' || mode === 'test') && (
              <div>
                <label
                  htmlFor="run-dialog-iterations"
                  className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  Iterations
                </label>
                <input
                  id="run-dialog-iterations"
                  type="number"
                  min={1}
                  max={100}
                  value={iterations}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => {
                    const v = parseInt(e.target.value, 10)
                    if (!isNaN(v)) setIterations(Math.min(100, Math.max(1, v)))
                  }}
                  className="w-24 rounded-lg border border-border bg-muted/40 px-3 py-2 text-xs tabular-nums text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground/70">
                  Number of {mode === 'train' ? 'training' : 'test'} iterations (1–100)
                </p>
              </div>
            )}

            {/* Filename (train only) */}
            {mode === 'train' && (
              <div>
                <label
                  htmlFor="run-dialog-filename"
                  className="mb-1.5 block text-[10px] font-semibold uppercase tracking-wider text-muted-foreground"
                >
                  Output File
                </label>
                <input
                  id="run-dialog-filename"
                  type="text"
                  value={filename}
                  onChange={(e: ChangeEvent<HTMLInputElement>) => setFilename(e.target.value)}
                  className="w-full rounded-lg border border-border bg-muted/40 px-3 py-2 font-mono text-xs text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  placeholder="training_data.pkl"
                  spellCheck={false}
                  autoComplete="off"
                />
                <p className="mt-1 text-xs text-muted-foreground/70">
                  Training data will be saved to this file (.pkl)
                </p>
              </div>
            )}

            {/* Inputs */}
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
                Press {modKey}+Enter to {config.verb.toLowerCase()}
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
                <button className="rounded-md border border-border px-4 py-2 text-xs font-medium text-muted-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  Cancel
                </button>
              </Dialog.Close>
              <button
                onClick={handleRun}
                disabled={!!error || loading}
                aria-busy={loading}
                aria-label={
                  loading ? `${config.verb}ing crew ${crewName}` : `${config.verb} crew ${crewName}`
                }
                className={`flex items-center gap-2 rounded-md px-4 py-2 text-xs font-semibold text-white shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 ${BUTTON_COLORS[mode]}`}
              >
                {loading ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                ) : (
                  <Icon className="h-3.5 w-3.5" />
                )}
                {loading ? config.verbLoading : config.verb}
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
