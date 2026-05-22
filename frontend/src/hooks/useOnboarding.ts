import { useState, useCallback } from 'react'
import { STORAGE_KEYS } from '@/lib/utils'

export function useOnboarding() {
  const [show, setShow] = useState(() => {
    return !localStorage.getItem(STORAGE_KEYS.ONBOARDING_COMPLETED)
  })

  const dismiss = useCallback(() => {
    localStorage.setItem(STORAGE_KEYS.ONBOARDING_COMPLETED, 'true')
    setShow(false)
  }, [])

  return { showOnboarding: show, dismissOnboarding: dismiss }
}
