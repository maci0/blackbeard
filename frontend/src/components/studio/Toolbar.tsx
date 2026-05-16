import { useState, type ChangeEvent } from 'react'
import { Save, Play, Loader2, FolderOpen, ChevronDown, Undo2, Redo2, Command } from 'lucide-react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { toResourceName } from '@/lib/utils'
import { modKey } from '@/lib/platform'
import type { RunStatus } from '@/lib/types'
import { RunStatusBadge } from './RunStatusBadge'
import { KeyboardShortcuts } from './KeyboardShortcuts'

export function Toolbar({
  crewName,
  onCrewNameChange,
  onSave,
  onRunClick,
  onLoadCrew,
  onFetchCrews,
  crews,
  crewsLoading,
  dirty,
  status,
  statusMessage,
  executionId,
  onNavigateToExecution,
  canUndo,
  canRedo,
  undo,
  redo,
}: {
  crewName: string
  onCrewNameChange: (v: string) => void
  onSave: () => void
  onRunClick: () => void
  onLoadCrew: (name: string) => void
  onFetchCrews: () => void
  crews: string[]
  crewsLoading?: boolean
  dirty: boolean
  status: RunStatus
  statusMessage: string
  executionId?: string | null
  onNavigateToExecution?: () => void
  canUndo: boolean
  canRedo: boolean
  undo: () => void
  redo: () => void
}) {
  const [shortcutsOpen, setShortcutsOpen] = useState(false)

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b bg-card px-2 sm:gap-3 sm:px-4">
      {/* Crew name + Load button */}
      <div className="flex min-w-0 flex-1 items-center gap-2">
        <label
          htmlFor="crew-name-input"
          className="shrink-0 cursor-default text-[10px] font-bold uppercase tracking-widest text-muted-foreground"
        >
          Crew
        </label>
        <input
          id="crew-name-input"
          data-tour="crew-name"
          type="text"
          value={crewName}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onCrewNameChange(e.target.value)}
          className="w-44 min-w-0 border-b border-transparent bg-transparent text-sm font-semibold text-foreground transition-colors placeholder:text-muted-foreground invalid:border-destructive invalid:text-destructive hover:border-border focus-visible:border-primary focus-visible:outline-none"
          placeholder="crew-name"
          spellCheck={false}
          autoComplete="off"
          pattern="[a-z0-9][a-z0-9\-]*"
          aria-describedby="crew-name-hint"
          title="Lowercase letters, numbers, and hyphens"
        />

        {/* Normalized name preview */}
        {crewName && toResourceName(crewName) !== crewName ? (
          <span
            id="crew-name-hint"
            className="hidden shrink-0 text-[10px] text-muted-foreground sm:inline"
            title="Resource name will be saved as this slug"
            aria-label={`Resource name will be saved as ${toResourceName(crewName)}`}
          >
            Saved as: {toResourceName(crewName)}
          </span>
        ) : (
          <span id="crew-name-hint" className="sr-only">
            Lowercase letters, numbers, and hyphens
          </span>
        )}

        {/* Load crew dropdown */}
        <DropdownMenu.Root
          onOpenChange={(open) => {
            if (open) onFetchCrews()
          }}
        >
          <DropdownMenu.Trigger asChild>
            <button
              aria-label="Load saved crew"
              className="text-2xs flex shrink-0 items-center gap-1 rounded-md border border-border px-2 py-1 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <FolderOpen className="h-3 w-3" />
              Load
              <ChevronDown className="h-3 w-3" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={6}
              align="start"
              className="bg-popover z-50 min-w-[200px] rounded-lg border border-border py-1 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
            >
              {crewsLoading ? (
                <div className="text-2xs flex items-center gap-2 px-3 py-2.5 text-muted-foreground">
                  <Loader2 className="h-3 w-3 animate-spin motion-reduce:animate-none" />
                  Loading…
                </div>
              ) : crews.length === 0 ? (
                <div className="text-2xs px-3 py-2.5 italic text-muted-foreground">
                  No saved crews yet — build one on the canvas and hit Save
                </div>
              ) : (
                crews.map((crewItem) => (
                  <DropdownMenu.Item
                    key={crewItem}
                    onSelect={() => onLoadCrew(crewItem)}
                    className="mx-1 cursor-pointer rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
                  >
                    {crewItem}
                  </DropdownMenu.Item>
                ))
              )}
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {/* Status badge — aria-live so screen readers announce state changes */}
      <div role="status" aria-live="polite" className="flex items-center">
        {status !== 'idle' && (
          <RunStatusBadge
            status={status}
            message={statusMessage}
            executionId={executionId}
            onNavigate={onNavigateToExecution}
          />
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Undo / Redo */}
        <button
          onClick={undo}
          disabled={!canUndo}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-30"
          aria-label="Undo"
          title={`Undo (${modKey}+Z)`}
        >
          <Undo2 className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={redo}
          disabled={!canRedo}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-30"
          aria-label="Redo"
          title={`Redo (${modKey}+Shift+Z)`}
        >
          <Redo2 className="h-3.5 w-3.5" />
        </button>

        <button
          data-tour="save-button"
          onClick={onSave}
          disabled={status === 'saving' || status === 'loading'}
          title={`Save (${modKey}+S)`}
          aria-label={`Save crew${dirty ? ' (unsaved changes)' : ''}`}
          className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
        >
          {status === 'saving' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <Save className="h-3.5 w-3.5" />
          )}
          Save
          {dirty && (
            <>
              <span className="ml-0.5 h-1.5 w-1.5 rounded-full bg-amber-400" aria-hidden="true" />
              <span className="sr-only">(unsaved changes)</span>
            </>
          )}
        </button>

        <button
          data-tour="run-button"
          onClick={onRunClick}
          disabled={status === 'running' || status === 'saving' || status === 'loading'}
          title={
            status === 'running'
              ? 'Crew is already running'
              : status === 'saving'
                ? 'Saving in progress…'
                : status === 'loading'
                  ? 'Loading crew…'
                  : 'Run this crew'
          }
          className="flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-600"
        >
          {status === 'running' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <Play className="h-3.5 w-3.5" />
          )}
          Run
        </button>

        {/* Keyboard shortcuts */}
        <button
          onClick={() => setShortcutsOpen(true)}
          aria-label="Keyboard shortcuts"
          title={`Keyboard shortcuts (${modKey}+/)`}
          className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Command className="h-3.5 w-3.5" />
        </button>
      </div>

      <KeyboardShortcuts open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </header>
  )
}
