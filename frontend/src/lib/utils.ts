import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

export function capitalize(s: string): string {
  return s.length > 0 ? s.charAt(0).toUpperCase() + s.slice(1) : ''
}

export function toResourceName(s: string): string {
  return (
    s
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/^-+|-+$/g, '') || 'unnamed'
  )
}

export function parseRef(ref: string): string {
  const idx = ref.lastIndexOf('/')
  return idx >= 0 ? ref.slice(idx + 1) : ref
}

export function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export const STORAGE_KEYS = {
  ONBOARDING_COMPLETED: 'blackbeard_onboarding_completed',
  TOUR_COMPLETED: 'blackbeard_tour_completed',
  SIDEBAR_COLLAPSED: 'blackbeard_sidebar_collapsed',
  NAMESPACE: 'blackbeard_namespace',
} as const
