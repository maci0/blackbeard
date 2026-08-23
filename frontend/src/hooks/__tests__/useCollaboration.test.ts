import { act } from 'react'
import { renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useCollaboration } from '../useCollaboration'

/**
 * Minimal WebSocket double capturing constructed instances so tests can
 * drive connection lifecycle events (open/close) deterministically.
 */
class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []
  url: string
  readyState = 0
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onerror: ((ev: unknown) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  sent: string[] = []

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(data)
  }

  close(): void {
    this.readyState = 3
  }
}

describe('useCollaboration reconnect lifecycle', () => {
  let originalWebSocket: typeof WebSocket

  beforeEach(() => {
    vi.useFakeTimers()
    originalWebSocket = globalThis.WebSocket
    FakeWebSocket.instances = []
    ;(globalThis as { WebSocket: unknown }).WebSocket = FakeWebSocket
  })

  afterEach(() => {
    vi.useRealTimers()
    ;(globalThis as { WebSocket: unknown }).WebSocket = originalWebSocket
    vi.restoreAllMocks()
  })

  function openSocket(ws: FakeWebSocket | undefined): void {
    if (!ws) throw new Error('expected a WebSocket instance')
    act(() => {
      ws.readyState = FakeWebSocket.OPEN
      ws.onopen?.()
    })
  }

  function closeSocket(ws: FakeWebSocket | undefined): void {
    if (!ws) throw new Error('expected a WebSocket instance')
    act(() => {
      ws.onclose?.()
    })
  }

  it('reconnects with backoff when the server closes while mounted', () => {
    const { unmount } = renderHook(() => useCollaboration('test-crew', true))
    expect(FakeWebSocket.instances).toHaveLength(1)

    openSocket(FakeWebSocket.instances[0])
    closeSocket(FakeWebSocket.instances[0])
    // First retry is scheduled at RECONNECT_DELAY_MS = 1000
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(FakeWebSocket.instances).toHaveLength(2)
    unmount()
  })

  it('does not schedule a zombie reconnect after unmount', () => {
    const { unmount } = renderHook(() => useCollaboration('test-crew', true))
    expect(FakeWebSocket.instances).toHaveLength(1)

    const first = FakeWebSocket.instances[0]
    openSocket(first)
    // Component unmounts first; the browser fires onclose asynchronously
    // afterwards on the closing socket.
    unmount()
    closeSocket(first)

    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    // No ghost reconnection to the old room may be created.
    expect(FakeWebSocket.instances).toHaveLength(1)
  })

  it('stops reconnecting after crew switch teardown closes the old socket', () => {
    const { rerender, unmount } = renderHook(
      ({ crew }: { crew: string }) => useCollaboration(crew, true),
      { initialProps: { crew: 'crew-a' } },
    )
    const first = FakeWebSocket.instances[0]
    openSocket(first)

    rerender({ crew: 'crew-b' })
    // Effect cleanup closed the old socket; its async onclose must not
    // resurrect a connection for crew-a.
    closeSocket(first)
    act(() => {
      vi.advanceTimersByTime(60_000)
    })

    // Only one additional socket exists and it targets the new crew.
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(FakeWebSocket.instances[1]?.url.includes('crew-b')).toBe(true)
    unmount()
  })
})
