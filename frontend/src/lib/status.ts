const STATUS_DISPLAY: Record<string, string> = {
  queued: 'Queued',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  cancelled: 'Cancelled',
  pending: 'Pending',
}

export const statusLabel = (status: string): string =>
  STATUS_DISPLAY[status] ?? status.charAt(0).toUpperCase() + status.slice(1)
