import { useState, useCallback, useEffect, useRef, useMemo, type ChangeEvent } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { AlertCircle, Check } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { canvasToYaml, yamlToCanvas } from './yamlSync'

const DEBOUNCE_MS = 300

type SyncStatus = 'synced' | 'editing' | 'error'

export function YamlEditor() {
  const nodes = useStudioStore((s) => s.nodes)
  const setNodes = useStudioStore((s) => s.setNodes)
  const setEdges = useStudioStore((s) => s.setEdges)

  // Extract only id+type+data per node so position-only changes (dragging)
  // don't trigger expensive JSON.stringify + YAML re-generation.
  const nodeDataSlice = useStudioStore(
    useShallow((s) => s.nodes.map((n) => ({ id: n.id, type: n.type, data: n.data }))),
  )

  const nodeDataFingerprint = useMemo(
    () => nodeDataSlice.map((n) => `${n.id}:${n.type}:${JSON.stringify(n.data)}`).join('|'),
    [nodeDataSlice],
  )

  const [yamlText, setYamlText] = useState(() => canvasToYaml(nodes))
  const [syncStatus, setSyncStatus] = useState<SyncStatus>('synced')
  const [parseError, setParseError] = useState<string | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isExternalUpdateRef = useRef(false)
  const isTypingRef = useRef(false)

  // When canvas node data changes externally (not from YAML edits), update the YAML text.
  // Keyed on nodeDataFingerprint so position-only changes (dragging) are ignored.
  useEffect(() => {
    if (isTypingRef.current) return
    const newYaml = canvasToYaml(nodes)
    isExternalUpdateRef.current = true
    setYamlText(newYaml)
    setSyncStatus('synced')
    setParseError(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodeDataFingerprint])

  const handleYamlChange = useCallback(
    (e: ChangeEvent<HTMLTextAreaElement>) => {
      const value = e.target.value
      isTypingRef.current = true
      isExternalUpdateRef.current = false
      setYamlText(value)
      setSyncStatus('editing')
      setParseError(null)

      if (debounceRef.current) clearTimeout(debounceRef.current)

      debounceRef.current = setTimeout(() => {
        if (value.trim() === '') {
          setNodes([])
          setEdges([])
          setSyncStatus('synced')
          isTypingRef.current = false
          return
        }

        const result = yamlToCanvas(value, useStudioStore.getState().nodes)
        if (result) {
          setNodes(result.nodes)
          setEdges(result.edges)
          setSyncStatus('synced')
          setParseError(null)
        } else {
          setSyncStatus('error')
          setParseError('Invalid YAML — check your syntax')
        }
        isTypingRef.current = false
      }, DEBOUNCE_MS)
    },
    [setNodes, setEdges],
  )

  // Clean up debounce timer on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [])

  return (
    <div className="flex h-full flex-col border-l bg-card" role="region" aria-label="YAML editor">
      {/* Header */}
      <div className="flex shrink-0 items-center justify-between border-b px-3 py-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          YAML
        </span>
        <div className="flex items-center gap-1.5">
          {syncStatus === 'synced' && (
            <span className="flex items-center gap-1 text-[10px] text-emerald-600 dark:text-emerald-400">
              <Check className="h-3 w-3" aria-hidden="true" />
              Synced
            </span>
          )}
          {syncStatus === 'editing' && (
            <span className="text-[10px] text-muted-foreground">Parsing…</span>
          )}
          {syncStatus === 'error' && (
            <span className="flex items-center gap-1 text-[10px] text-destructive">
              <AlertCircle className="h-3 w-3" aria-hidden="true" />
              Error
            </span>
          )}
        </div>
      </div>

      {/* Editor */}
      <div className="relative min-h-0 flex-1">
        <textarea
          value={yamlText}
          onChange={handleYamlChange}
          className="h-full w-full resize-none bg-[#0d1117] p-4 font-mono text-xs leading-relaxed text-slate-300 focus-visible:outline-none"
          spellCheck={false}
          autoComplete="off"
          autoCapitalize="off"
          autoCorrect="off"
          aria-label="YAML source editor"
          aria-describedby={parseError ? 'yaml-parse-error' : undefined}
          aria-invalid={syncStatus === 'error' ? true : undefined}
          placeholder={`apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find key facts
  backstory: You research topics.`}
        />
      </div>

      {/* Error bar */}
      {parseError && (
        <div
          id="yaml-parse-error"
          role="alert"
          className="flex items-center gap-1.5 border-t border-destructive/30 bg-destructive/5 px-3 py-2"
        >
          <AlertCircle className="h-3 w-3 shrink-0 text-destructive" />
          <span className="text-xs text-destructive">{parseError}</span>
        </div>
      )}
    </div>
  )
}
