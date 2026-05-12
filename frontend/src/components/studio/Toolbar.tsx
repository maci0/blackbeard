import { type ChangeEvent, useMemo } from 'react'
import { Save, Play, Loader2, FolderOpen, ChevronDown, Undo2, Redo2, Loader } from 'lucide-react'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { toResourceName } from '@/lib/utils'
import { type RunStatus, RunStatusBadge } from './RunStatusBadge'

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

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
  const mod = useMemo(() => /Mac|iPhone|iPad/.test(navigator.userAgent) ? 'Cmd' : 'Ctrl', [])

  return (
    <header className="h-12 shrink-0 border-b bg-card flex items-center gap-3 px-4">
      {/* Crew name + Load button */}
      <div className="flex items-center gap-2 flex-1 min-w-0">
        <label
          htmlFor="crew-name-input"
          className="text-[10px] font-bold text-muted-foreground uppercase tracking-widest shrink-0 cursor-default"
        >
          Crew
        </label>
        <input
          id="crew-name-input"
          data-tour="crew-name"
          type="text"
          value={crewName}
          onChange={(e: ChangeEvent<HTMLInputElement>) => onCrewNameChange(e.target.value)}
          className="min-w-0 w-44 text-sm font-semibold bg-transparent border-b border-transparent hover:border-border focus:border-primary focus:outline-none text-foreground placeholder:text-muted-foreground transition-colors"
          placeholder="crew-name"
          spellCheck={false}
        />

        {/* Normalized name preview */}
        {crewName && toResourceName(crewName) !== crewName && (
          <span
            className="text-[10px] text-muted-foreground shrink-0"
            title="Resource name will be saved as this slug"
          >
            Saved as: {toResourceName(crewName)}
          </span>
        )}

        {/* Load crew dropdown */}
        <DropdownMenu.Root onOpenChange={(open) => { if (open) onFetchCrews() }}>
          <DropdownMenu.Trigger asChild>
            <button className="flex items-center gap-1 px-2 py-1 text-[11px] font-medium text-muted-foreground border border-border rounded-md hover:bg-muted hover:text-foreground transition-colors shrink-0">
              <FolderOpen className="w-3 h-3" />
              Load
              <ChevronDown className="w-3 h-3" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={6}
              align="start"
              className="z-50 min-w-[200px] bg-popover border border-border rounded-lg shadow-xl py-1 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=open]:fade-in-0 data-[state=closed]:fade-out-0 data-[state=open]:zoom-in-95 data-[state=closed]:zoom-out-95"
            >
              {crewsLoading ? (
                <div className="px-3 py-2.5 text-[11px] text-muted-foreground flex items-center gap-2">
                  <Loader className="w-3 h-3 animate-spin motion-reduce:animate-none" />
                  Loading…
                </div>
              ) : crews.length === 0 ? (
                <div className="px-3 py-2.5 text-[11px] text-muted-foreground italic">
                  No saved crews found
                </div>
              ) : (
                crews.map((crewItem) => (
                  <DropdownMenu.Item
                    key={crewItem}
                    onSelect={() => onLoadCrew(crewItem)}
                    className="px-3 py-2 text-[12px] font-medium cursor-pointer text-foreground hover:bg-muted focus:bg-muted focus:outline-none rounded-sm mx-1 transition-colors"
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
        {status === 'idle' ? (
          <span className="sr-only">Ready</span>
        ) : (
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
          className="p-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-30 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          aria-label="Undo"
          title={`Undo (${mod}+Z)`}
        >
          <Undo2 className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={redo}
          disabled={!canRedo}
          className="p-1.5 rounded-lg border border-border hover:bg-muted disabled:opacity-30 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
          aria-label="Redo"
          title={`Redo (${mod}+Shift+Z)`}
        >
          <Redo2 className="h-3.5 w-3.5" />
        </button>

        <button
          data-tour="save-button"
          onClick={onSave}
          disabled={status === 'saving' || status === 'loading'}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold border border-border rounded-lg text-foreground bg-background hover:bg-muted disabled:opacity-50 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {status === 'saving' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <Save className="w-3.5 h-3.5" />
          )}
          Save
          {dirty && <span className="w-1.5 h-1.5 rounded-full bg-amber-400 ml-0.5" />}
        </button>

        <button
          data-tour="run-button"
          onClick={onRunClick}
          disabled={status === 'running' || status === 'saving' || status === 'loading'}
          className="flex items-center gap-1.5 px-3 py-1.5 text-[12px] font-semibold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50 transition-colors shadow-sm focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
        >
          {status === 'running' ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin motion-reduce:animate-none" />
          ) : (
            <Play className="w-3.5 h-3.5" />
          )}
          Run
        </button>
      </div>
    </header>
  )
}
