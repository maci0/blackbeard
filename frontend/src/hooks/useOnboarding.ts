import { useState, useCallback } from 'react'

const STORAGE_KEY = 'blackbeard_onboarding_completed'

export function useOnboarding() {
  const [show, setShow] = useState(() => {
    return !localStorage.getItem(STORAGE_KEY)
  })

  const dismiss = useCallback(() => {
    localStorage.setItem(STORAGE_KEY, 'true')
    setShow(false)
  }, [])

  return { showOnboarding: show, dismissOnboarding: dismiss }
}
