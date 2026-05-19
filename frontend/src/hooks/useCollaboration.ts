import { useState, useEffect, useRef, useCallback } from 'react'
import { useStudioStore } from '@/stores/studioStore'
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
}

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

/** Reconnect delay in milliseconds. */
const RECONNECT_DELAY_MS = 2000
/** Maximum reconnect attempts before giving up. */
const MAX_RECONNECT_ATTEMPTS = 5

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
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectAttemptsRef = useRef(0)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  /** Flag to suppress re-broadcasting incoming remote changes. */
  const applyingRemoteRef = useRef(false)

  useEffect(() => {
    if (!enabled || !crewName) {
      // Clean up any existing connection when disabled
      if (wsRef.current) {
        wsRef.current.close()
        wsRef.current = null
      }
      setConnected(false)
      setParticipants(1)
      return
    }

    function connect() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      const ws = new WebSocket(
        `${protocol}//${window.location.host}/api/v1/ws/collab/${encodeURIComponent(crewName)}`,
      )
      wsRef.current = ws

      ws.onopen = () => {
        setConnected(true)
        reconnectAttemptsRef.current = 0
      }

      ws.onclose = () => {
        setConnected(false)
        setParticipants(1)
        wsRef.current = null

        // Auto-reconnect with backoff
        if (enabled && reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
          reconnectAttemptsRef.current += 1
          reconnectTimeoutRef.current = setTimeout(connect, RECONNECT_DELAY_MS)
        }
      }

      ws.onerror = () => {
        // onclose will fire after onerror, handling reconnection
      }

      ws.onmessage = (event: MessageEvent) => {
        try {
          const msg = JSON.parse(event.data as string) as CollabMessage
          handleIncoming(msg)
        } catch {
          // Ignore malformed messages
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
    }
  }, [crewName, enabled])

  const broadcast = useCallback((type: string, data: Record<string, unknown>) => {
    // Don't re-broadcast changes that came from the network
    if (applyingRemoteRef.current) return
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type, data }))
    }
  }, [])

  function handleIncoming(msg: CollabMessage) {
    const store = useStudioStore.getState()

    switch (msg.type) {
      case 'node_add': {
        applyingRemoteRef.current = true
        try {
          store.addNode(msg.data as unknown as Node)
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'node_move': {
        const { id, position } = msg.data as { id: string; position: { x: number; y: number } }
        applyingRemoteRef.current = true
        try {
          useStudioStore.setState((state) => ({
            nodes: state.nodes.map((n) => (n.id === id ? { ...n, position } : n)),
          }))
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'node_delete': {
        applyingRemoteRef.current = true
        try {
          store.removeNode(msg.data['id'] as string)
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'node_update': {
        applyingRemoteRef.current = true
        try {
          store.updateNodeData(
            msg.data['id'] as string,
            msg.data['data'] as Record<string, unknown>,
          )
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'edge_add': {
        applyingRemoteRef.current = true
        try {
          useStudioStore.setState((state) => ({
            edges: [...state.edges, msg.data as unknown as Edge],
          }))
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'edge_delete': {
        applyingRemoteRef.current = true
        try {
          const edgeId = msg.data['id'] as string
          useStudioStore.setState((state) => ({
            edges: state.edges.filter((e) => e.id !== edgeId),
          }))
        } finally {
          applyingRemoteRef.current = false
        }
        break
      }

      case 'participant_joined':
      case 'participant_left':
      case 'room_state':
        setParticipants((msg.data['count'] as number) ?? 1)
        break

      // cursor_move and selection_change could be handled here for
      // presence features — skipped for MVP
    }
  }

  return { participants, connected, broadcast }
}
