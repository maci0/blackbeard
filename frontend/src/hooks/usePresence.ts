import { useState, useEffect, useRef, useCallback } from 'react'
import { TOKEN_KEY } from '@/stores/authStore'

interface PresenceUser {
  id: string
  name: string
}

interface UsePresenceReturn {
  users: PresenceUser[]
  connected: boolean
}

const MAX_RECONNECT_DELAY_MS = 30_000
const INITIAL_RECONNECT_DELAY_MS = 1_000
/** Maximum reconnect attempts before giving up, matching useCollaboration. */
const MAX_RECONNECT_ATTEMPTS = 5

export function usePresence(roomId: string | null): UsePresenceReturn {
  const [users, setUsers] = useState<PresenceUser[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectDelayRef = useRef(INITIAL_RECONNECT_DELAY_MS)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const mountedRef = useRef(true)

  const cleanup = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnected(false)
    setUsers([])
    reconnectAttemptsRef.current = 0
    reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS
  }, [])

  useEffect(() => {
    mountedRef.current = true
    if (!roomId) {
      cleanup()
      return
    }

    function connect() {
      if (!mountedRef.current || !roomId) return

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = localStorage.getItem(TOKEN_KEY) ?? ''
      const authParam = token ? `?token=${encodeURIComponent(token)}` : ''
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/api/v1/collaboration/rooms/${encodeURIComponent(roomId)}${authParam}`,
      )
      wsRef.current = ws

      ws.onopen = () => {
        if (!mountedRef.current) return
        setConnected(true)
        reconnectAttemptsRef.current = 0
        reconnectDelayRef.current = INITIAL_RECONNECT_DELAY_MS

        let id = 'anonymous'
        let name = 'Anonymous'
        if (token) {
          try {
            const payload = JSON.parse(atob(token.split('.')[1] ?? '{}')) as {
              sub?: string
              display_name?: string
            }
            id = payload.sub ?? 'anonymous'
            name = payload.display_name ?? 'Anonymous'
          } catch {
            console.warn('[presence] malformed JWT token')
          }
        }

        ws.send(JSON.stringify({ type: 'join', user: { id, name } }))
      }

      ws.onmessage = (event: MessageEvent) => {
        if (!mountedRef.current) return
        try {
          const msg = JSON.parse(event.data as string) as {
            type: string
            users?: PresenceUser[]
          }
          if (msg.type === 'presence' && msg.users) {
            setUsers(msg.users)
          }
        } catch (err) {
          console.debug('[presence] malformed WebSocket message:', err)
        }
      }

      ws.onclose = () => {
        if (!mountedRef.current) return
        setConnected(false)
        wsRef.current = null

        if (reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS) {
          console.warn('[presence] giving up after max reconnect attempts')
          return
        }
        reconnectAttemptsRef.current += 1
        const delay = reconnectDelayRef.current
        reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS)
        reconnectTimeoutRef.current = setTimeout(connect, delay)
      }

      ws.onerror = () => {
        console.warn('[presence] WebSocket error (onclose will follow)')
      }
    }

    connect()

    return () => {
      mountedRef.current = false
      cleanup()
    }
  }, [roomId, cleanup])

  return { users, connected }
}
