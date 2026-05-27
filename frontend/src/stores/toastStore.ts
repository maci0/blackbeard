import { create } from 'zustand'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
  dismissing?: boolean
}

interface ToastState {
  toasts: Toast[]
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
  dismiss: (id: string) => void
  pause: (id: string) => void
  resume: (id: string) => void
}

let counter = 0

const DURATIONS: Record<Toast['type'], number> = {
  success: 5000,
  error: 15000,
  info: 7000,
}

const timers = new Map<
  string,
  { timeoutId: ReturnType<typeof setTimeout>; remaining: number; startedAt: number }
>()

function removeToast(id: string) {
  timers.delete(id)
  useToastStore.setState((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
}

function dismissToast(id: string) {
  const timer = timers.get(id)
  if (timer) clearTimeout(timer.timeoutId)
  useToastStore.setState((s) => ({
    toasts: s.toasts.map((t) => (t.id === id ? { ...t, dismissing: true } : t)),
  }))
  setTimeout(() => removeToast(id), 300)
}

function startTimer(id: string, duration: number) {
  const timeoutId = setTimeout(() => dismissToast(id), duration)
  timers.set(id, { timeoutId, remaining: duration, startedAt: Date.now() })
}

function addToast(type: Toast['type'], message: string) {
  const id = `toast-${++counter}-${Date.now()}`
  useToastStore.setState((s) => ({ toasts: [...s.toasts, { id, type, message }] }))
  startTimer(id, DURATIONS[type])
}

export const useToastStore = create<ToastState>(() => ({
  toasts: [],
  success: (message: string) => addToast('success', message),
  error: (message: string) => addToast('error', message),
  info: (message: string) => addToast('info', message),
  dismiss: (id: string) => dismissToast(id),
  pause: (id: string) => {
    const timer = timers.get(id)
    if (!timer) return
    clearTimeout(timer.timeoutId)
    timer.remaining = Math.max(timer.remaining - (Date.now() - timer.startedAt), 0)
  },
  resume: (id: string) => {
    const timer = timers.get(id)
    if (!timer || timer.remaining <= 0) return
    startTimer(id, timer.remaining)
  },
}))
