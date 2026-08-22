import { useEffect, useRef } from 'react'

export function usePolling(
  callback: () => Promise<void>,
  intervalMs: number,
  enabled: boolean,
): void {
  const savedCallback = useRef(callback)
  useEffect(() => {
    savedCallback.current = callback
  }, [callback])

  useEffect(() => {
    if (!enabled) return
    let active = true
    let timeoutId: ReturnType<typeof setTimeout>
    const tick = () => {
      if (!active) return
      // Skip API calls while the tab is hidden; keep the loop alive so
      // polling resumes on its own (plus immediately via visibilitychange).
      if (document.hidden) {
        timeoutId = setTimeout(tick, intervalMs)
        return
      }
      void savedCallback
        .current()
        .catch((err: unknown) => {
          console.warn('[usePolling] callback failed:', err)
        })
        .finally(() => {
          if (active) timeoutId = setTimeout(tick, intervalMs)
        })
    }
    const onVisible = () => {
      if (!active || document.hidden) return
      clearTimeout(timeoutId)
      tick()
    }
    document.addEventListener('visibilitychange', onVisible)
    timeoutId = setTimeout(tick, intervalMs)
    return () => {
      active = false
      clearTimeout(timeoutId)
      document.removeEventListener('visibilitychange', onVisible)
    }
  }, [intervalMs, enabled])
}
