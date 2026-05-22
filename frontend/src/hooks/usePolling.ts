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
      void savedCallback
        .current()
        .catch((err: unknown) => {
          console.warn('[usePolling] callback failed:', err)
        })
        .finally(() => {
          if (active) timeoutId = setTimeout(tick, intervalMs)
        })
    }
    timeoutId = setTimeout(tick, intervalMs)
    return () => {
      active = false
      clearTimeout(timeoutId)
    }
  }, [intervalMs, enabled])
}
