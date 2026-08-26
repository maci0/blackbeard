import { useState, useCallback, type ChangeEvent } from 'react'
import {
  Save,
  Play,
  Loader2,
  FolderOpen,
  ChevronDown,
  Undo2,
  Redo2,
  Keyboard,
  FileCode2,
  LayoutGrid,
  Users,
  Radio,
  Sparkles,
  Download,
  ClipboardCopy,
  XCircle,
  Settings,
  Image,
  FileType,
} from 'lucide-react'
import { toPng, toSvg } from 'html-to-image'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { NAME_PATTERN } from '@/lib/kinds'
import { toResourceName } from '@/lib/utils'
import { modKey } from '@/lib/platform'
import { useStudioStore } from '@/stores/studioStore'
import { useToastStore } from '@/stores/toastStore'
import type { RunStatus } from '@/lib/types'
import { Tooltip } from '@/components/ui/Tooltip'
import { RunStatusBadge } from './RunStatusBadge'
import { KeyboardShortcuts } from './KeyboardShortcuts'
import { PresenceAvatars } from '@/components/ui/PresenceAvatars'

export function Toolbar({
  crewName,
  onCrewNameChange,
  onSave,
  onRunClick,
  onLoadCrew,
  onFetchCrews,
  crews,
  crewsLoading,
  crewsFetchError,
  dirty,
  status,
  statusMessage,
  executionId,
  onNavigateToExecution,
  canUndo,
  canRedo,
  undo,
  redo,
  yamlOpen,
  onYamlToggle,
  onAutoLayout,
  layouting,
  onAssistantClick,
  collabEnabled,
  onCollabToggle,
  collabConnected,
  collabParticipants,
  presenceUsers,
  hasExecResults,
  onClearExecResults,
  onCrewSettingsClick,
}: {
  crewName: string
  onCrewNameChange: (v: string) => void
  onSave: () => void
  onRunClick: () => void
  onLoadCrew: (name: string) => void
  onFetchCrews: () => void
  crews: string[]
  crewsLoading?: boolean
  crewsFetchError?: boolean
  dirty: boolean
  status: RunStatus
  statusMessage: string
  executionId?: string | null
  onNavigateToExecution?: () => void
  canUndo: boolean
  canRedo: boolean
  undo: () => void
  redo: () => void
  yamlOpen: boolean
  onYamlToggle: () => void
  onAutoLayout: () => void
  layouting?: boolean
  onAssistantClick: () => void
  collabEnabled?: boolean
  onCollabToggle?: () => void
  collabConnected?: boolean
  collabParticipants?: number
  presenceUsers?: Array<{ id: string; name: string }>
  hasExecResults?: boolean
  onClearExecResults?: () => void
  onCrewSettingsClick: () => void
}) {
  const [shortcutsOpen, setShortcutsOpen] = useState(false)
  const toasts = useToastStore()

  const getExportData = useCallback(() => {
    const { nodes, edges } = useStudioStore.getState()
    return JSON.stringify({ crewName, nodes, edges }, null, 2)
  }, [crewName])

  const downloadBlob = useCallback((dataUrl: string, filename: string) => {
    const a = document.createElement('a')
    a.href = dataUrl
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  }, [])

  const handleExportJSON = useCallback(() => {
    const json = getExportData()
    const blob = new Blob([json], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    downloadBlob(url, `${toResourceName(crewName) || 'crew'}.json`)
    URL.revokeObjectURL(url)
    toasts.success('Exported as JSON')
  }, [crewName, getExportData, toasts, downloadBlob])

  const handleCopyJSON = useCallback(async () => {
    const json = getExportData()
    try {
      await navigator.clipboard.writeText(json)
      toasts.success('Copied to clipboard')
    } catch {
      toasts.error('Failed to copy to clipboard')
    }
  }, [getExportData, toasts])

  const getReactFlowElement = useCallback((): HTMLElement | null => {
    return document.querySelector<HTMLElement>('.react-flow')
  }, [])

  const handleExportPNG = useCallback(async () => {
    const el = getReactFlowElement()
    if (!el) {
      toasts.error('Canvas element not found')
      return
    }
    try {
      const dataUrl = await toPng(el, {
        backgroundColor: '#ffffff',
        pixelRatio: 2,
      })
      downloadBlob(dataUrl, `${toResourceName(crewName) || 'crew'}.png`)
      toasts.success('Exported as PNG')
    } catch (err) {
      console.error('[studio] PNG export failed:', err)
      toasts.error('PNG export failed')
    }
  }, [crewName, getReactFlowElement, downloadBlob, toasts])

  const handleExportSVG = useCallback(async () => {
    const el = getReactFlowElement()
    if (!el) {
      toasts.error('Canvas element not found')
      return
    }
    try {
      const dataUrl = await toSvg(el, {
        backgroundColor: '#ffffff',
      })
      downloadBlob(dataUrl, `${toResourceName(crewName) || 'crew'}.svg`)
      toasts.success('Exported as SVG')
    } catch (err) {
      console.error('[studio] SVG export failed:', err)
      toasts.error('SVG export failed')
    }
  }, [crewName, getReactFlowElement, downloadBlob, toasts])

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
          pattern={NAME_PATTERN}
          aria-describedby="crew-name-hint"
          title="Lowercase letters, numbers, and hyphens"
        />

        {/* Normalized name preview */}
        {crewName && toResourceName(crewName) !== crewName ? (
          <span
            id="crew-name-hint"
            className="shrink-0 text-[10px] text-muted-foreground"
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
              type="button"
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
              ) : crewsFetchError ? (
                <div className="text-2xs px-3 py-2.5 italic text-red-500">
                  Failed to load crews: check connection
                </div>
              ) : crews.length === 0 ? (
                <div className="text-2xs px-3 py-2.5 italic text-muted-foreground">
                  No saved crews yet: build one on the canvas and hit Save
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

      {/* Status badge: aria-live so screen readers announce state changes */}
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
        <Tooltip content={`Undo (${modKey}+Z)`}>
          <button
            type="button"
            onClick={undo}
            disabled={!canUndo}
            className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            aria-label="Undo"
          >
            <Undo2 className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
        <Tooltip content={`Redo (${modKey}+Shift+Z)`}>
          <button
            type="button"
            onClick={redo}
            disabled={!canRedo}
            className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
            aria-label="Redo"
          >
            <Redo2 className="h-3.5 w-3.5" />
          </button>
        </Tooltip>

        <Tooltip content={`Save (${modKey}+S)`}>
          <button
            type="button"
            data-tour="save-button"
            onClick={onSave}
            disabled={status === 'saving' || status === 'loading'}
            aria-label={`Save crew${dirty ? ' (unsaved changes)' : ''}`}
            className="btn-press flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-semibold text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
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
        </Tooltip>

        <Tooltip
          content={
            status === 'running'
              ? 'Crew is already running'
              : status === 'saving'
                ? 'Saving in progress...'
                : status === 'loading'
                  ? 'Loading crew...'
                  : 'Run this crew'
          }
        >
          <button
            type="button"
            data-tour="run-button"
            onClick={onRunClick}
            disabled={status === 'running' || status === 'saving' || status === 'loading'}
            aria-label={`Run crew ${crewName}`}
            className="btn-press flex items-center gap-1.5 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition-colors hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 dark:bg-emerald-500 dark:hover:bg-emerald-600"
          >
            {status === 'running' ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
            ) : (
              <Play className="h-3.5 w-3.5" />
            )}
            Run
          </button>
        </Tooltip>

        {hasExecResults && onClearExecResults && (
          <Tooltip content="Clear execution results">
            <button
              type="button"
              onClick={onClearExecResults}
              aria-label="Clear execution results from canvas"
              className="flex items-center gap-1.5 rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <XCircle className="h-3.5 w-3.5" />
              Clear results
            </button>
          </Tooltip>
        )}

        {/* Crew settings */}
        <Tooltip content="Crew Settings">
          <button
            type="button"
            onClick={onCrewSettingsClick}
            aria-label="Crew settings"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
        </Tooltip>

        {/* AI Assistant */}
        <Tooltip content="Generate crew from prompt">
          <button
            type="button"
            onClick={onAssistantClick}
            disabled={status === 'saving' || status === 'loading'}
            aria-label="AI Assistant, generate crew from prompt"
            className="flex items-center gap-1.5 rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-700 transition-colors hover:bg-amber-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50 dark:border-amber-700 dark:bg-amber-950/50 dark:text-amber-300 dark:hover:bg-amber-950"
          >
            <Sparkles className="h-3.5 w-3.5" aria-hidden="true" />
            Assistant
          </button>
        </Tooltip>

        {/* Export dropdown */}
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              type="button"
              aria-label="Export crew"
              className="flex items-center gap-1 rounded-lg border border-border bg-background px-2.5 py-1.5 text-xs font-semibold text-foreground transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <Download className="h-3.5 w-3.5" />
              Export
              <ChevronDown className="h-3 w-3" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              sideOffset={6}
              align="end"
              className="bg-popover z-50 min-w-[180px] rounded-lg border border-border py-1 shadow-xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
            >
              <DropdownMenu.Item
                onSelect={handleExportJSON}
                className="mx-1 flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
              >
                <Download className="h-3.5 w-3.5 text-muted-foreground" />
                Export JSON
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => void handleCopyJSON()}
                className="mx-1 flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
              >
                <ClipboardCopy className="h-3.5 w-3.5 text-muted-foreground" />
                Copy as JSON
              </DropdownMenu.Item>
              <DropdownMenu.Separator className="mx-2 my-1 h-px bg-border" />
              <DropdownMenu.Item
                onSelect={() => void handleExportPNG()}
                className="mx-1 flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
              >
                <Image className="h-3.5 w-3.5 text-muted-foreground" />
                Export PNG
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => void handleExportSVG()}
                className="mx-1 flex cursor-pointer items-center gap-2 rounded-sm px-3 py-2 text-xs font-medium text-foreground transition-colors hover:bg-muted focus:bg-muted focus:outline-none"
              >
                <FileType className="h-3.5 w-3.5 text-muted-foreground" />
                Export SVG
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        {/* YAML editor toggle */}
        <Tooltip content="Toggle YAML editor">
          <button
            type="button"
            onClick={onYamlToggle}
            aria-label={yamlOpen ? 'Close YAML editor' : 'Open YAML editor'}
            aria-pressed={yamlOpen}
            className={`flex h-[44px] w-[44px] items-center justify-center rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              yamlOpen
                ? 'border-primary bg-primary/10 text-primary'
                : 'border-border hover:bg-muted'
            }`}
          >
            <FileCode2 className="h-3.5 w-3.5" />
          </button>
        </Tooltip>

        {/* Auto layout */}
        <Tooltip content="Auto layout">
          <button
            type="button"
            onClick={onAutoLayout}
            disabled={layouting}
            aria-label="Auto-arrange nodes"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-50"
          >
            {layouting ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
            ) : (
              <LayoutGrid className="h-3.5 w-3.5" />
            )}
          </button>
        </Tooltip>

        {/* Collaboration toggle + participant count */}
        {onCollabToggle && (
          <div className="flex items-center gap-1.5">
            <Tooltip
              content={
                collabEnabled
                  ? 'Collaboration active, click to disconnect'
                  : 'Enable live collaboration'
              }
            >
              <button
                type="button"
                onClick={onCollabToggle}
                aria-label={
                  collabEnabled ? 'Disable live collaboration' : 'Enable live collaboration'
                }
                aria-pressed={collabEnabled}
                className={`flex h-[44px] w-[44px] items-center justify-center rounded-lg border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
                  collabEnabled && collabConnected
                    ? 'border-emerald-500 bg-emerald-500/10 text-emerald-500'
                    : collabEnabled
                      ? 'border-amber-500 bg-amber-500/10 text-amber-500'
                      : 'border-border hover:bg-muted'
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
              </button>
            </Tooltip>
            {collabEnabled && collabConnected && (collabParticipants ?? 1) > 1 && (
              <span
                className="flex items-center gap-1 text-xs font-medium text-emerald-500"
                aria-label={`${collabParticipants} collaborators connected`}
              >
                <Users className="h-3 w-3" aria-hidden="true" />
                {collabParticipants}
              </span>
            )}
          </div>
        )}

        {presenceUsers && presenceUsers.length > 0 && <PresenceAvatars users={presenceUsers} />}

        {/* Keyboard shortcuts */}
        <Tooltip content={`Keyboard shortcuts (${modKey}+/)`}>
          <button
            type="button"
            onClick={() => setShortcutsOpen(true)}
            aria-label="Keyboard shortcuts"
            className="flex h-[44px] w-[44px] items-center justify-center rounded-lg border border-border transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Keyboard className="h-3.5 w-3.5" />
          </button>
        </Tooltip>
      </div>

      <KeyboardShortcuts open={shortcutsOpen} onOpenChange={setShortcutsOpen} />
    </header>
  )
}
