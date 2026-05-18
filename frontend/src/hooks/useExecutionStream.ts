import { useEffect, useRef, useState, useCallback } from 'react'

export interface StreamEvent {
  event: string
  data: Record<string, unknown>
}

interface UseExecutionStreamOptions {
  executionId: string | undefined
  enabled?: boolean
  onEvent?: (event: StreamEvent) => void
  onStatusChange?: (data: Record<string, unknown>) => void
}

type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'error'

export function useExecutionStream({
  executionId,
  enabled = true,
  onEvent,
  onStatusChange,
}: UseExecutionStreamOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>('disconnected')
  const [lastEvent, setLastEvent] = useState<StreamEvent | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const disconnect = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }
    setConnectionState('disconnected')
  }, [])

  useEffect(() => {
    if (!executionId || !enabled) {
      disconnect()
      return
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const url = `${protocol}//${host}/api/v1/executions/${executionId}/ws`

    setConnectionState('connecting')

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setConnectionState('connected')
    }

    ws.onmessage = (msg) => {
      try {
        const parsed = JSON.parse(msg.data as string) as StreamEvent
        setLastEvent(parsed)
        onEvent?.(parsed)

        if (parsed.event === 'status') {
          onStatusChange?.(parsed.data)
        }
      } catch {
        // ignore malformed messages
      }
    }

    ws.onclose = (ev) => {
      if (ev.code === 4004) {
        setConnectionState('error')
      } else {
        setConnectionState('disconnected')
      }
      wsRef.current = null
    }

    ws.onerror = () => {
      setConnectionState('error')
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [executionId, enabled, disconnect, onEvent, onStatusChange])

  return { connectionState, lastEvent, disconnect }
}
