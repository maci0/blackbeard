import { create } from 'zustand'

export interface AppNotification {
  id: string
  title: string
  body: string
  time: Date
  read: boolean
}

interface NotificationState {
  unreadCount: number
  notifications: AppNotification[]
  add: (title: string, body: string) => void
  markAllRead: () => void
  clear: () => void
}

const MAX_NOTIFICATIONS = 50

let counter = 0

export const useNotificationStore = create<NotificationState>((set) => ({
  unreadCount: 0,
  notifications: [],

  add: (title: string, body: string) => {
    const notification: AppNotification = {
      id: `notif-${++counter}-${Date.now()}`,
      title,
      body,
      time: new Date(),
      read: false,
    }
    set((s) => ({
      notifications: [notification, ...s.notifications].slice(0, MAX_NOTIFICATIONS),
      unreadCount: s.unreadCount + 1,
    }))
  },

  markAllRead: () =>
    set((s) => ({
      unreadCount: 0,
      notifications: s.notifications.map((n) => ({ ...n, read: true })),
    })),

  clear: () => set({ notifications: [], unreadCount: 0 }),
}))
