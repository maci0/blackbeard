import { useState, useEffect, useCallback, useMemo } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api } from '@/api/client'
import type { Resource } from '@/lib/types'

interface CrewSettings {
  onErrorCrew: string
  onErrorAction: string
}

interface CrewSettingsDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  settings: CrewSettings
  onSave: (settings: CrewSettings) => void
  currentCrewName: string
}

const ACTION_OPTIONS = [
  { value: '', label: 'No action' },
  { value: 'run', label: 'Run error crew' },
  { value: 'retry', label: 'Retry failed crew' },
  { value: 'ignore', label: 'Ignore error' },
]

export function CrewSettingsDialog({
  open,
  onOpenChange,
  settings,
  onSave,
  currentCrewName,
}: CrewSettingsDialogProps) {
  const [localSettings, setLocalSettings] = useState<CrewSettings>(settings)
  const [crews, setCrews] = useState<Resource[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      setLocalSettings(settings)
      setLoading(true)
      void api
        .get<{ items: Resource[]; total: number }>('/api/v1/crews')
        .then((result) => setCrews(result.items))
        .catch(() => setCrews([]))
        .finally(() => setLoading(false))
    }
  }, [open, settings])

  const crewOptions = useMemo(
    () => [
      { value: '', label: 'None' },
      ...crews
        .filter((c) => c.metadata.name !== currentCrewName)
        .map((c) => ({
          value: `ref:crews/${c.metadata.name}`,
          label: c.metadata.name,
        })),
    ],
    [crews, currentCrewName],
  )

  const handleSave = useCallback(() => {
    onSave(localSettings)
    onOpenChange(false)
  }, [localSettings, onSave, onOpenChange])

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content
          aria-describedby="crew-settings-desc"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          <Dialog.Title className="text-lg font-semibold">Crew Settings</Dialog.Title>
          <Dialog.Description
            id="crew-settings-desc"
            className="mt-1 text-sm text-muted-foreground"
          >
            Configure error handling behavior for this crew.
          </Dialog.Description>

          <div className="mt-5 space-y-4">
            <div className="space-y-1.5">
              <label
                htmlFor="crew-settings-action"
                className="block text-xs font-semibold tracking-wide text-muted-foreground"
              >
                On Error Action
              </label>
              <select
                id="crew-settings-action"
                className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                value={localSettings.onErrorAction}
                onChange={(e) =>
                  setLocalSettings((prev) => ({ ...prev, onErrorAction: e.target.value }))
                }
              >
                {ACTION_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
            </div>

            {localSettings.onErrorAction === 'run' && (
              <div className="space-y-1.5">
                <label
                  htmlFor="crew-settings-error-crew"
                  className="block text-xs font-semibold tracking-wide text-muted-foreground"
                >
                  Error Crew
                </label>
                {loading ? (
                  <p className="text-xs text-muted-foreground">Loading crews...</p>
                ) : crewOptions.length <= 1 ? (
                  <p className="text-xs text-muted-foreground">
                    No other crews available. Save a crew first.
                  </p>
                ) : (
                  <select
                    id="crew-settings-error-crew"
                    className="w-full rounded-md border border-border bg-background px-2.5 py-2 text-sm text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                    value={localSettings.onErrorCrew}
                    onChange={(e) =>
                      setLocalSettings((prev) => ({ ...prev, onErrorCrew: e.target.value }))
                    }
                  >
                    {crewOptions.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </select>
                )}
                <p className="text-xs text-muted-foreground">
                  Select a crew to run when this crew fails.
                </p>
              </div>
            )}
          </div>

          <div className="mt-6 flex justify-end gap-3">
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Cancel
              </button>
            </Dialog.Close>
            <button
              type="button"
              onClick={handleSave}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Save Settings
            </button>
          </div>

          <Dialog.Close asChild>
            <button
              type="button"
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
