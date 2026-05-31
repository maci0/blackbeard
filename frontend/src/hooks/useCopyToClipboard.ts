import { useState, useCallback, useRef } from 'react'

export function useCopyToClipboard(feedbackMs = 2000) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text)
      } catch {
        console.warn('[useCopyToClipboard] clipboard.writeText failed')
        return
      }
      if (timerRef.current) clearTimeout(timerRef.current)
      setCopied(true)
      timerRef.current = setTimeout(() => setCopied(false), feedbackMs)
    },
    [feedbackMs],
  )

  return { copied, copy } as const
}
