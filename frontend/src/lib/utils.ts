/** Shared UI helpers: class names, locale strings, storage keys, errors. */

import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/** Locale-aware first-letter capitalization (handles Turkish İ/i, etc.). */
export function capitalize(s: string): string {
  return s.length > 0 ? s.charAt(0).toLocaleUpperCase() + s.slice(1) : ''
}

/**
 * Locale-aware case fold for search/filter matching.
 * Prefer this over toLowerCase() so Turkish and other locales compare correctly.
 */
export function caseFold(s: string): string {
  return s.toLocaleLowerCase()
}

/** Locale-aware string comparison for user-facing sorted lists. */
export function compareStrings(a: string, b: string): number {
  return a.localeCompare(b, undefined, { sensitivity: 'base' })
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

export function getErrorMessage(err: unknown, fallback: string): string {
  return err instanceof Error ? err.message : fallback
}

export const STORAGE_KEYS = {
  ONBOARDING_COMPLETED: 'blackbeard_onboarding_completed',
  TOUR_COMPLETED: 'blackbeard_tour_completed',
  SIDEBAR_COLLAPSED: 'blackbeard_sidebar_collapsed',
  PROJECT: 'blackbeard_project',
} as const

export const STORAGE_KEYS_NAV = {
  COLLAPSED_SECTIONS: 'blackbeard_nav_collapsed_sections',
} as const
