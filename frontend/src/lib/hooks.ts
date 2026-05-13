import { useState, useEffect, useRef } from 'react'

export function useDocumentTitle(title: string): void {
  useEffect(() => {
    document.title = `${title} | Blackbeard`
    return () => { document.title = 'Blackbeard' }
  }, [title])
}

export function usePolling(
  callback: () => Promise<void>,
  intervalMs: number,
  enabled: boolean,
): void {
  const savedCallback = useRef(callback)
  useEffect(() => { savedCallback.current = callback }, [callback])

  useEffect(() => {
    if (!enabled) return
    const id = setInterval(() => { void savedCallback.current() }, intervalMs)
    return () => clearInterval(id)
  }, [intervalMs, enabled])
}

export function useDarkMode(): boolean {
  const [dark, setDark] = useState(() =>
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-color-scheme: dark)').matches,
  )
  useEffect(() => {
    const mq = window.matchMedia('(prefers-color-scheme: dark)')
    const handler = (e: MediaQueryListEvent) => setDark(e.matches)
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
  }, [dark])
  return dark
}
