import { useState, useEffect, useRef } from 'react'

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} | Blackbeard`
    return () => {
      document.title = 'Blackbeard'
    }
  }, [title])
}

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
    const mountedRef = { current: true }
    const id = setInterval(() => {
      if (mountedRef.current) {
        void savedCallback.current()
      }
    }, intervalMs)
    return () => {
      mountedRef.current = false
      clearInterval(id)
    }
  }, [intervalMs, enabled])
}

export type ThemePreference = 'system' | 'dark' | 'light'

function readStoredTheme(): ThemePreference {
  if (typeof window === 'undefined') return 'system'
  const stored = localStorage.getItem('theme')
  if (stored === 'dark' || stored === 'light') return stored
  return 'system'
}

export function useDarkMode(): { isDark: boolean; preference: ThemePreference; cycle: () => void } {
  const [preference, setPreference] = useState<ThemePreference>(readStoredTheme)
  const [systemDark, setSystemDark] = useState(
    () =>
      typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches,
  )

  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setSystemDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  const isDark = preference === 'dark' ? true : preference === 'light' ? false : systemDark

  useEffect(() => {
    document.documentElement.classList.toggle('dark', isDark)
  }, [isDark])

  const cycle = () => {
    setPreference((prev) => {
      const next: ThemePreference =
        prev === 'system' ? 'dark' : prev === 'dark' ? 'light' : 'system'
      localStorage.setItem('theme', next)
      return next
    })
  }

  return { isDark, preference, cycle }
}
