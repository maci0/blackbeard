import { create } from 'zustand'

export interface Toast {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

interface ToastState {
  toasts: Toast[]
  success: (message: string) => void
  error: (message: string) => void
  info: (message: string) => void
  dismiss: (id: string) => void
}

let counter = 0

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],

  success: (message: string) => {
    const id = `toast-${++counter}-${Date.now()}`
    set((s) => ({ toasts: [...s.toasts, { id, type: 'success', message }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },

  error: (message: string) => {
    const id = `toast-${++counter}-${Date.now()}`
    set((s) => ({ toasts: [...s.toasts, { id, type: 'error', message }] }))
  },

  info: (message: string) => {
    const id = `toast-${++counter}-${Date.now()}`
    set((s) => ({ toasts: [...s.toasts, { id, type: 'info', message }] }))
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
    }, 4000)
  },

  dismiss: (id: string) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }))
  },
}))
