import { useState, useCallback, useRef } from 'react'

export function useCopyToClipboard(feedbackMs = 2000) {
  const [copied, setCopied] = useState(false)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const copy = useCallback(
    async (text: string) => {
      await navigator.clipboard.writeText(text)
      if (timerRef.current) clearTimeout(timerRef.current)
      setCopied(true)
      timerRef.current = setTimeout(() => setCopied(false), feedbackMs)
    },
    [feedbackMs],
  )

  return { copied, copy } as const
}
