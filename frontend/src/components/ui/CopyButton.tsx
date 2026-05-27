import { useState, useCallback } from 'react'
import { Copy, Check, X } from 'lucide-react'
import { cn } from '@/lib/utils'

export function CopyButton({
  text,
  label = 'Copy to clipboard',
  className,
}: {
  text: string
  label?: string
  className?: string
}) {
  const [state, setState] = useState<'idle' | 'copied' | 'failed'>('idle')

  const handleCopy = useCallback(() => {
    void navigator.clipboard
      .writeText(text)
      .then(() => {
        setState('copied')
        setTimeout(() => setState('idle'), 2000)
      })
      .catch(() => {
        setState('failed')
        setTimeout(() => setState('idle'), 2000)
      })
  }, [text])

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={state === 'copied' ? 'Copied' : state === 'failed' ? 'Copy failed' : label}
      className={cn(
        'inline-flex h-8 w-8 items-center justify-center rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        className,
      )}
    >
      {state === 'copied' ? (
        <Check className="h-3.5 w-3.5 text-emerald-500" />
      ) : state === 'failed' ? (
        <X className="h-3.5 w-3.5 text-red-500" />
      ) : (
        <Copy className="h-3.5 w-3.5" />
      )}
    </button>
  )
}
