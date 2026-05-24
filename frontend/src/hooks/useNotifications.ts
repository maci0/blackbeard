import { useEffect, useCallback, useRef, useState } from 'react'

type NotificationPermission = 'default' | 'denied' | 'granted'

export function useNotifications() {
  const [permission, setPermission] = useState<NotificationPermission>(
    typeof Notification !== 'undefined' ? Notification.permission : 'denied',
  )
  const requested = useRef(false)

  useEffect(() => {
    if (typeof Notification === 'undefined' || requested.current) return
    if (Notification.permission === 'default') {
      requested.current = true
      void Notification.requestPermission().then((p) => setPermission(p))
    }
  }, [])

  const notify = useCallback(
    (title: string, body?: string) => {
      if (typeof Notification === 'undefined' || permission !== 'granted') return
      try {
        new Notification(title, { body, icon: '/favicon.ico' })
      } catch {
        /* falls back silently */
      }
    },
    [permission],
  )

  return { notify, permission }
}
