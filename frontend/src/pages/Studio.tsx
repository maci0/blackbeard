import { useState, useCallback, useEffect, useRef } from 'react'
import { ReactFlowProvider, MarkerType } from '@xyflow/react'
import { useNavigate } from 'react-router-dom'
import { useStudioStore } from '@/stores/studioStore'
import { api } from '@/api/client'
import { capitalize, toResourceName } from '@/lib/utils'
import { KIND_TO_PLURAL } from '@/lib/kinds'
import Palette from '@/components/studio/Palette'
import Canvas from '@/components/studio/Canvas'
import PropertyPanel from '@/components/studio/PropertyPanel'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { type RunStatus } from '@/components/studio/RunStatusBadge'
import { RunDialog } from '@/components/studio/RunDialog'
import { Toolbar } from '@/components/studio/Toolbar'
import type { Node, Edge } from '@xyflow/react'
import type { Resource } from '@/stores/resourceStore'

/* ------------------------------------------------------------------ */
/* Resource body builder                                               */
/* ------------------------------------------------------------------ */

function buildResourceBody(node: Node, crewName: string) {
  const data = node.data as Record<string, unknown>
  const type = node.type ?? 'unknown'

  const rawName =
    (data['role'] as string | undefined) ??
    (data['name'] as string | undefined) ??
    node.id

  return {
    apiVersion: 'blackbeard/v1',
    kind: capitalize(type),
    metadata: {
      name: toResourceName(rawName),
      labels: { crew: crewName },
    },
    spec: data,
  }
}

/* ------------------------------------------------------------------ */
/* Ref parser                                                          */
/* ------------------------------------------------------------------ */

function parseRef(ref: string): string {
  // "ref:agents/my-agent" → "my-agent"
  const idx = ref.lastIndexOf('/')
  return idx >= 0 ? ref.slice(idx + 1) : ref
}

/* ------------------------------------------------------------------ */
/* Studio inner — uses the ReactFlowProvider context from parent       */
/* ------------------------------------------------------------------ */

function StudioInner() {
  const navigate = useNavigate()
  const [crewName, setCrewName] = useState('my-crew')
  const [runDialogOpen, setRunDialogOpen] = useState(false)
  const [status, setStatus] = useState<RunStatus>('idle')
  const [statusMessage, setStatusMessage] = useState('')
  const [executionId, setExecutionId] = useState<string | null>(null)
  const [crews, setCrews] = useState<string[]>([])
  const [crewsLoading, setCrewsLoading] = useState(false)
  const [pendingLoadCrew, setPendingLoadCrew] = useState<string | null>(null)

  const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { nodes, selectedNodeId, setNodes, setEdges, markClean, dirty, canUndo, canRedo, undo, redo } =
    useStudioStore()

  /* ── Document title ── */
  useEffect(() => {
    document.title = 'Studio | Blackbeard'
    return () => { document.title = 'Blackbeard' }
  }, [])

  /* ── Clear timeout on unmount ── */
  useEffect(() => {
    return () => {
      if (statusTimeoutRef.current) clearTimeout(statusTimeoutRef.current)
    }
  }, [])

  /* ── Unsaved changes warning ── */
  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (useStudioStore.getState().dirty) {
        e.preventDefault()
      }
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [])

  /* ── Status helper with auto-dismiss for 'success' ── */
  const applyStatus = useCallback((newStatus: RunStatus, message: string) => {
    if (statusTimeoutRef.current) {
      clearTimeout(statusTimeoutRef.current)
      statusTimeoutRef.current = null
    }
    setStatus(newStatus)
    setStatusMessage(message)
    if (newStatus === 'success') {
      statusTimeoutRef.current = setTimeout(() => {
        setStatus('idle')
        setStatusMessage('')
        statusTimeoutRef.current = null
      }, 5000)
    }
  }, [])

  /* ── Fetch saved crews for the Load dropdown ── */
  const fetchCrews = useCallback(async () => {
    setCrewsLoading(true)
    try {
      const result = await api.get<{ items: Resource[]; total: number }>('/api/v1/crews')
      setCrews(result.items.map((c) => c.metadata.name))
    } catch {
      setCrews([])
    } finally {
      setCrewsLoading(false)
    }
  }, [])

  /* ── Load an existing crew onto the canvas (core logic) ── */
  const doLoadCrew = useCallback(
    async (name: string) => {
      applyStatus('loading', `Loading "${name}"…`)
      try {
        const crew = await api.get<Resource>(`/api/v1/crews/${name}`)

        const agentNames = ((crew.spec.agents as string[] | undefined) ?? []).map(parseRef)
        const taskNames = ((crew.spec.tasks as string[] | undefined) ?? []).map(parseRef)

        const [agentResources, taskResources] = await Promise.all([
          Promise.all(agentNames.map((n) => api.get<Resource>(`/api/v1/agents/${n}`))),
          Promise.all(taskNames.map((n) => api.get<Resource>(`/api/v1/tasks/${n}`))),
        ])

        // Build nodes — agents on left, tasks in middle
        const agentNodes: Node[] = agentResources.map((agent, i) => ({
          id: `agent-${agent.metadata.name}`,
          type: 'agent',
          position: { x: 100, y: 80 + i * 230 },
          data: { ...agent.spec },
        }))

        const taskNodes: Node[] = taskResources.map((task, i) => ({
          id: `task-${task.metadata.name}`,
          type: 'task',
          position: { x: 460, y: 80 + i * 230 },
          data: { ...task.spec },
        }))

        // Build edges: task.spec.agent ref → agent node
        const edges: Edge[] = taskResources
          .filter((task) => typeof task.spec.agent === 'string' && task.spec.agent)
          .map((task) => {
            const agentName = parseRef(task.spec.agent as string)
            return {
              id: `edge-agent-${agentName}-task-${task.metadata.name}`,
              source: `agent-${agentName}`,
              target: `task-${task.metadata.name}`,
              type: 'dataflow',
              markerEnd: {
                type: MarkerType.ArrowClosed,
                width: 12,
                height: 12,
                color: '#94a3b8',
              },
            } satisfies Edge
          })

        setNodes([...agentNodes, ...taskNodes])
        setEdges(edges)
        setCrewName(crew.metadata.name)
        markClean()
        applyStatus('success', `Loaded "${name}"`)
      } catch (err) {
        applyStatus('error', err instanceof Error ? err.message : 'Load failed')
      }
    },
    [applyStatus, markClean, setEdges, setNodes],
  )

  /* ── Guard: if dirty, show confirm dialog; otherwise load immediately ── */
  const handleLoadCrew = useCallback(
    (name: string) => {
      const { dirty } = useStudioStore.getState()
      if (dirty) {
        setPendingLoadCrew(name)
        return
      }
      void doLoadCrew(name)
    },
    [doLoadCrew],
  )

  /* ── Save all nodes to the API ── */
  const handleSave = useCallback(async (): Promise<boolean> => {
    if (nodes.length === 0) {
      applyStatus('error', 'Nothing to save — add some nodes first')
      return false
    }
    applyStatus('saving', 'Saving…')
    try {
      await Promise.all(
        nodes.map((node) => {
          const body = buildResourceBody(node, crewName)
          const plural = KIND_TO_PLURAL[capitalize(node.type ?? '')] ?? `${node.type ?? 'resource'}s`
          return api.post(`/api/v1/${plural}`, body)
        }),
      )

      // Synthesize and save the Crew resource
      const agentNodes = nodes.filter((n) => n.type === 'agent')
      const taskNodes = nodes.filter((n) => n.type === 'task')
      const agentRefs = agentNodes.map((n) => {
        const d = n.data as Record<string, unknown>
        const raw = (d['role'] as string | undefined) ?? (d['name'] as string | undefined) ?? n.id
        return `ref:agents/${toResourceName(raw)}`
      })
      const taskRefs = taskNodes.map((n) => {
        const d = n.data as Record<string, unknown>
        const raw = (d['name'] as string | undefined) ?? n.id
        return `ref:tasks/${toResourceName(raw)}`
      })
      const crewBody = {
        apiVersion: 'blackbeard/v1',
        kind: 'Crew',
        metadata: { name: toResourceName(crewName) },
        spec: {
          process: 'sequential',
          agents: agentRefs,
          tasks: taskRefs,
        },
      }
      await api.post('/api/v1/crews', crewBody)

      markClean()
      applyStatus(
        'success',
        `Saved ${nodes.length} resource${nodes.length !== 1 ? 's' : ''} + crew`,
      )
      return true
    } catch (err) {
      applyStatus('error', err instanceof Error ? err.message : 'Save failed')
      return false
    }
  }, [nodes, crewName, applyStatus, markClean])

  /* ── Run the crew (auto-saves first) ── */
  const handleRun = useCallback(
    async (rawInputs: string) => {
      setRunDialogOpen(false)
      setExecutionId(null)

      // Auto-save before running
      const saved = await handleSave()
      if (!saved) return

      applyStatus('running', 'Starting execution…')
      try {
        let parsedInputs: Record<string, unknown> = {}
        try {
          parsedInputs = JSON.parse(rawInputs) as Record<string, unknown>
        } catch {
          // keep empty inputs
        }
        const result = await api.post<{ id: string }>(
          `/api/v1/crews/${toResourceName(crewName)}/kickoff`,
          { inputs: parsedInputs },
        )
        setExecutionId(result.id)
        applyStatus('success', 'Execution started →')
      } catch (err) {
        applyStatus('error', err instanceof Error ? err.message : 'Run failed')
      }
    },
    [crewName, handleSave, applyStatus],
  )

  return (
    <div className="flex flex-col h-full">
      <Toolbar
        crewName={crewName}
        onCrewNameChange={setCrewName}
        onSave={handleSave}
        onRunClick={() => setRunDialogOpen(true)}
        onLoadCrew={handleLoadCrew}
        onFetchCrews={fetchCrews}
        crews={crews}
        crewsLoading={crewsLoading}
        dirty={dirty}
        status={status}
        statusMessage={statusMessage}
        executionId={executionId}
        onNavigateToExecution={
          executionId ? () => navigate(`/executions/${executionId}`) : undefined
        }
        canUndo={canUndo}
        canRedo={canRedo}
        undo={undo}
        redo={redo}
      />

      <div className="flex flex-1 overflow-hidden">
        <Palette />
        <Canvas onLoadExample={() => handleLoadCrew('research-crew')} />
        {selectedNodeId && <PropertyPanel />}
      </div>

      <RunDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        crewName={crewName}
        onRun={handleRun}
      />

      <ConfirmDialog
        open={!!pendingLoadCrew}
        onOpenChange={(open) => { if (!open) setPendingLoadCrew(null) }}
        title="Discard unsaved changes?"
        description="Loading a crew will replace your current canvas. Unsaved changes will be lost."
        confirmLabel="Discard & Load"
        confirmVariant="destructive"
        onConfirm={() => {
          if (pendingLoadCrew) void doLoadCrew(pendingLoadCrew)
          setPendingLoadCrew(null)
        }}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Exported page — provides ReactFlowProvider for all children         */
/* ------------------------------------------------------------------ */

export default function Studio() {
  return (
    <ReactFlowProvider>
      <StudioInner />
    </ReactFlowProvider>
  )
}
