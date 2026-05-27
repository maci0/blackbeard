import { useCallback, useEffect, useRef, useState } from 'react'

const DISMISS_TIMEOUT_MS = 8000

export function useDeleteError() {
  const [deleteError, setDeleteError] = useState<string | null>(null)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
    }
  }, [])

  const showDeleteError = useCallback((message: string) => {
    setDeleteError(message)
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => setDeleteError(null), DISMISS_TIMEOUT_MS)
  }, [])

  const clearDeleteError = useCallback(() => {
    setDeleteError(null)
    if (timerRef.current) clearTimeout(timerRef.current)
  }, [])

  return { deleteError, showDeleteError, clearDeleteError } as const
}
