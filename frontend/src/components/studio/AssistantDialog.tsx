import { useState, useRef, useEffect } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X, Sparkles, AlertCircle, Check } from 'lucide-react'
import { Spinner } from '@/components/ui/Spinner'
import { api } from '@/api/client'

interface AssistantResource {
  apiVersion: string
  kind: string
  metadata: { name: string; [k: string]: unknown }
  spec: Record<string, unknown>
}

interface AssistantResponse {
  resources: AssistantResource[]
  explanation: string
}

interface AssistantDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onApply: (resources: AssistantResource[]) => void
}

export type { AssistantResource }

export function AssistantDialog({ open, onOpenChange, onApply }: AssistantDialogProps) {
  const [prompt, setPrompt] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AssistantResponse | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Focus textarea when dialog opens
  useEffect(() => {
    if (open && textareaRef.current) {
      // Small delay to let the dialog animation start
      const timer = setTimeout(() => textareaRef.current?.focus(), 100)
      return () => clearTimeout(timer)
    }
  }, [open])

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setError(null)
      setResult(null)
    }
  }, [open])

  const handleGenerate = async () => {
    if (prompt.trim().length < 10) {
      setError('Prompt must be at least 10 characters.')
      return
    }

    setLoading(true)
    setError(null)
    setResult(null)

    try {
      const response = await api.post<AssistantResponse>('/api/v1/assistant/generate', {
        prompt: prompt.trim(),
      })
      setResult(response)
    } catch (err) {
      if (err instanceof Error) {
        setError(err.message)
      } else {
        setError('An unexpected error occurred.')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleApply = () => {
    if (result) {
      onApply(result.resources)
      onOpenChange(false)
      setPrompt('')
      setResult(null)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && !loading) {
      e.preventDefault()
      void handleGenerate()
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex w-full max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col rounded-lg border bg-card shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95">
          {/* Header */}
          <div className="flex items-center gap-2 border-b px-6 py-4">
            <Sparkles className="h-5 w-5 text-amber-400" aria-hidden="true" />
            <Dialog.Title className="text-lg font-semibold">AI Assistant</Dialog.Title>
          </div>

          {/* Body */}
          <div className="flex flex-col gap-4 px-6 py-4">
            <Dialog.Description className="text-sm text-muted-foreground">
              Describe the crew you want to build. The copilot will generate agents, tasks, and a
              crew definition for you.
            </Dialog.Description>

            <div>
              <label htmlFor="copilot-prompt" className="sr-only">
                Describe your crew
              </label>
              <textarea
                ref={textareaRef}
                id="copilot-prompt"
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="e.g. Build me a research crew that finds facts about a topic and writes a summary report..."
                rows={4}
                maxLength={5000}
                disabled={loading}
                className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
                aria-describedby={error ? 'copilot-error' : undefined}
              />
              <div className="mt-1 flex items-center justify-between">
                <span className="text-[10px] text-muted-foreground">
                  {prompt.length}/5000 characters
                </span>
                <span className="text-[10px] text-muted-foreground">
                  {navigator.platform.includes('Mac') ? 'Cmd' : 'Ctrl'}+Enter to generate
                </span>
              </div>
            </div>

            {/* Error message */}
            {error && (
              <div
                id="copilot-error"
                role="alert"
                className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/50 dark:text-red-400"
              >
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>{error}</span>
              </div>
            )}

            {/* Loading state */}
            {loading && (
              <div className="flex items-center justify-center gap-2 py-4 text-sm text-muted-foreground">
                <Spinner size="sm" label="Generating resources" />
                <span>Generating resources...</span>
              </div>
            )}

            {/* Result preview */}
            {result && (
              <div className="flex flex-col gap-3">
                <p className="text-sm font-medium text-emerald-600 dark:text-emerald-400">
                  {result.explanation}
                </p>
                <div className="max-h-48 overflow-y-auto rounded-md border bg-muted/50 p-3">
                  <ul className="space-y-2" aria-label="Generated resources">
                    {result.resources.map((resource, i) => (
                      <li
                        key={`${resource.kind}-${resource.metadata.name}-${String(i)}`}
                        className="flex items-center gap-2 text-sm"
                      >
                        <Check
                          className="h-3.5 w-3.5 shrink-0 text-emerald-500"
                          aria-hidden="true"
                        />
                        <span className="inline-flex items-center gap-1.5">
                          <span className="rounded bg-muted px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                            {resource.kind}
                          </span>
                          <span className="font-medium text-foreground">
                            {resource.metadata.name}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-end gap-3 border-t px-6 py-4">
            <Dialog.Close asChild>
              <button className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                Cancel
              </button>
            </Dialog.Close>

            {result ? (
              <button
                onClick={handleApply}
                className="inline-flex items-center gap-1.5 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring dark:bg-emerald-500 dark:hover:bg-emerald-600"
              >
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
                Apply to Canvas
              </button>
            ) : (
              <button
                onClick={() => void handleGenerate()}
                disabled={loading || prompt.trim().length < 10}
                aria-busy={loading}
                className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50 dark:bg-amber-400 dark:text-black dark:hover:bg-amber-500"
              >
                {loading ? (
                  <Spinner size="sm" className="text-current" label="Generating" />
                ) : (
                  <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                Generate
              </button>
            )}
          </div>

          {/* Close button */}
          <Dialog.Close asChild>
            <button
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
