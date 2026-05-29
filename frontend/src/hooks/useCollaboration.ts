import { useState, useEffect, useRef, useCallback } from 'react'
import { TOKEN_KEY } from '@/stores/authStore'
import { useStudioStore } from '@/stores/studioStore'
import type { RemoteCursor } from '@/components/studio/CursorOverlay'
import type { Node, Edge } from '@xyflow/react'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface CollabMessage {
  type: string
  data: Record<string, unknown>
}

interface UseCollaborationReturn {
  /** Number of participants in the collaboration room (including self). */
  participants: number
  /** Whether the WebSocket connection is currently open. */
  connected: boolean
  /** Send a collaboration message to other participants. */
  broadcast: (type: string, data: Record<string, unknown>) => void
  /** Throttled cursor position broadcast (call on every mousemove). */
  broadcastCursor: (data: Record<string, unknown>) => void
  /** Map of remote collaborator cursors keyed by userId. */
  remoteCursors: Map<string, RemoteCursor>
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

/** Initial reconnect delay in milliseconds. */
const RECONNECT_DELAY_MS = 1000
/** Maximum reconnect delay in milliseconds. */
const MAX_RECONNECT_DELAY_MS = 16000
/** Maximum reconnect attempts before giving up. */
const MAX_RECONNECT_ATTEMPTS = 5
/** Minimum interval between cursor broadcast messages (ms). */
const CURSOR_THROTTLE_MS = 50
/** Color palette for remote collaborators. */
const CURSOR_COLORS = ['#ef4444', '#3b82f6', '#22c55e', '#f59e0b', '#8b5cf6', '#ec4899']

/* ------------------------------------------------------------------ */
/* Hook                                                                */
/* ------------------------------------------------------------------ */

/**
 * Real-time collaboration hook for Studio canvas.
 *
 * Connects to the collaboration WebSocket endpoint and:
 * - Broadcasts local canvas changes to other participants
 * - Applies incoming changes from other participants to the local store
 * - Tracks participant count and connection state
 *
 * Incoming messages are applied with a `_remote` flag set on the store
 * to prevent re-broadcasting changes that originated from other users.
 */
export function useCollaboration(crewName: string, enabled: boolean): UseCollaborationReturn {
  const [participants, setParticipants] = useState(1)
  const [connected, setConnected] = useState(false)
  const [remoteCursors, setRemoteCursors] = useState<Map<string, RemoteCursor>>(new Map())
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Flag to suppress re-broadcasting incoming remote changes. */
  const applyingRemoteRef = useRef(false)
  /** Counter for assigning deterministic colors to new participants. */
  const colorIndexRef = useRef(0)
  /** Current reconnect delay for exponential backoff. */
  const reconnectDelayRef = useRef(RECONNECT_DELAY_MS)

  useEffect(() => {
    if (!enabled || !crewName) {
      // Clean up any existing connection when disabled
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setConnected(false)
      setParticipants(1)
      setRemoteCursors(new Map())
      colorIndexRef.current = 0
      return
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const token = localStorage.getItem(TOKEN_KEY) ?? ''
      const authParam = token ? `?token=${encodeURIComponent(token)}` : ''
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/api/v1/ws/collab/${encodeURIComponent(crewName)}${authParam}`,
      )
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectAttemptsRef.current = 0
        reconnectDelayRef.current = RECONNECT_DELAY_MS
      }

      ws.onclose = () => {
        setConnected(false)
        setParticipants(1)
        setRemoteCursors(new Map())
        wsRef.current = null

        if (enabled && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1
          const delay = reconnectDelayRef.current
          reconnectDelayRef.current = Math.min(delay * 2, MAX_RECONNECT_DELAY_MS)
          reconnectTimeoutRef.current = setTimeout(connect, delay)
        }
      }

      ws.onerror = (ev) => {
        console.warn('[collab] WebSocket error:', ev)
      }

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as CollabMessage
          handleIncoming(msg)
        } catch (err) {
          console.warn('[collab] malformed WebSocket message:', err)
        }
      }
    }

    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setConnected(false)
      setParticipants(1)
      setRemoteCursors(new Map())
      colorIndexRef.current = 0
    }
  }, [crewName, enabled])

  const broadcast = useCallback((type: string, data: Record<string, unknown>) => {
    // Don't re-broadcast changes that came from the network
    if (applyingRemoteRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }))
    }
  }, [])

  function applyRemote(fn: () => void) {
    applyingRemoteRef.current = true
    try {
      fn()
    } finally {
      applyingRemoteRef.current = false
    }
  }

  function handleIncoming(msg: CollabMessage) {
    const store = useStudioStore.getState()

    switch (msg.type) {
      case 'node_add': {
        applyRemote(() => store.addNode(msg.data as unknown as Node))
        break
      }

      case 'node_move': {
        const { id, position } = msg.data as { id: string; position: { x: number; y: number } }
        applyRemote(() =>
          useStudioStore.setState((state) => ({
            nodes: state.nodes.map((n) => (n.id === id ? { ...n, position } : n)),
          })),
        )
        break
      }

      case 'node_delete': {
        applyRemote(() => store.removeNode(msg.data['id'] as string))
        break
      }

      case 'node_update': {
        applyRemote(() =>
          store.updateNodeData(
            msg.data['id'] as string,
            msg.data['data'] as Record<string, unknown>,
          ),
        )
        break
      }

      case 'edge_add': {
        applyRemote(() =>
          useStudioStore.setState((state) => ({
            edges: [...state.edges, msg.data as unknown as Edge],
          })),
        )
        break
      }

      case 'edge_delete': {
        applyRemote(() => {
          const edgeId = msg.data['id'] as string
          useStudioStore.setState((state) => ({
            edges: state.edges.filter((e) => e.id !== edgeId),
          }))
        })
        break
      }

      case 'cursor_move': {
        const userId = msg.data['userId'] as string | undefined
        const name = msg.data['name'] as string | undefined
        const x = msg.data['x'] as number | undefined
        const y = msg.data['y'] as number | undefined
        if (userId && typeof x === 'number' && typeof y === 'number') {
          setRemoteCursors((prev) => {
            const existing = prev.get(userId)
            if (existing && existing.x === x && existing.y === y) return prev
            const color =
              existing?.color ??
              CURSOR_COLORS[colorIndexRef.current++ % CURSOR_COLORS.length] ??
              '#6b7280'
            const next = new Map(prev)
            next.set(userId, {
              userId,
              name: name ?? 'Anonymous',
              x,
              y,
              color,
            })
            return next
          })
        }
        break
      }

      case 'participant_joined':
      case 'room_state':
        setParticipants((msg.data['count'] as number) ?? 1)
        break

      case 'participant_left': {
        setParticipants((msg.data['count'] as number) ?? 1)
        // Clean up cursor for the departing user if their userId is provided
        const leftUserId = msg.data['userId'] as string | undefined
        if (leftUserId) {
          setRemoteCursors((prev) => {
            const next = new Map(prev)
            next.delete(leftUserId)
            return next
          })
        }
        break
      }
    }
  }

  /**
   * Throttled cursor broadcast. Call on every mousemove; only sends at
   * most once per CURSOR_THROTTLE_MS.
   */
  const lastCursorBroadcastRef = useRef(0)
  const broadcastCursor = useCallback(
    (data: Record<string, unknown>) => {
      const now = Date.now()
      if (now - lastCursorBroadcastRef.current < CURSOR_THROTTLE_MS) return
      lastCursorBroadcastRef.current = now
      broadcast('cursor_move', data)
    },
    [broadcast],
  )

  return { participants, connected, broadcast, broadcastCursor, remoteCursors }
}
