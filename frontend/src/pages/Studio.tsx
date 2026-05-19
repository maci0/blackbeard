import { useState, useCallback, useEffect, useRef } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { useNavigate } from 'react-router-dom'
import { useStudioStore } from '@/stores/studioStore'
import { api } from '@/api/client'
import { capitalize, toResourceName, parseRef } from '@/lib/utils'
import { useDocumentTitle } from '@/lib/hooks'
import { API_VERSION, KIND_TO_PLURAL } from '@/lib/kinds'
import { DATAFLOW_MARKER_END } from '@/components/studio/defaults'
import Palette, { MobilePalette } from '@/components/studio/Palette'
import Canvas from '@/components/studio/Canvas'
import PropertyPanel from '@/components/studio/PropertyPanel'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import type { RunStatus } from '@/lib/types'
import { RunDialog, type RunParams } from '@/components/studio/RunDialog'
import { Toolbar } from '@/components/studio/Toolbar'
import { YamlEditor } from '@/components/studio/YamlEditor'
import { autoLayout } from '@/components/studio/autoLayout'
import type { Node, Edge } from '@xyflow/react'
import type { Resource } from '@/lib/types'

/* ------------------------------------------------------------------ */
/* Resource body builder                                               */
/* ------------------------------------------------------------------ */

function buildResourceBody(node: Node, crewName: string) {
  const data = node.data
  const type = node.type ?? 'unknown'

  const rawName =
    (data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? node.id

  // 'name' is used for metadata.name, not a spec field — exclude to avoid validation failure
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { name: _unused, ...spec } = data

  return {
    apiVersion: API_VERSION,
    kind: capitalize(type),
    metadata: {
      name: toResourceName(rawName),
      labels: { crew: crewName },
    },
    spec,
  }
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
  const [yamlOpen, setYamlOpen] = useState(false)
  const [layouting, setLayouting] = useState(false)

  const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // Select individual slices to avoid re-rendering on every node position change.
  // NOTE: nodes is NOT subscribed here — handleSave reads it via getState() at
  // call time, avoiding re-renders on every drag frame.
  const selectedNodeId = useStudioStore((s) => s.selectedNodeId)
  const setNodes = useStudioStore((s) => s.setNodes)
  const setEdges = useStudioStore((s) => s.setEdges)
  const markClean = useStudioStore((s) => s.markClean)
  const dirty = useStudioStore((s) => s.dirty)
  const canUndo = useStudioStore((s) => s.canUndo)
  const canRedo = useStudioStore((s) => s.canRedo)
  const undo = useStudioStore((s) => s.undo)
  const redo = useStudioStore((s) => s.redo)

  useDocumentTitle('Studio')

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
          position: { x: 80, y: 60 + i * 200 },
          data: { ...agent.spec },
        }))

        const taskNodes: Node[] = taskResources.map((task, i) => ({
          id: `task-${task.metadata.name}`,
          type: 'task',
          position: { x: 360, y: 60 + i * 200 },
          data: { name: task.metadata.name, ...task.spec },
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
              markerEnd: DATAFLOW_MARKER_END,
            } satisfies Edge
          })

        const allNodes = [...agentNodes, ...taskNodes]
        try {
          const laid = await autoLayout(allNodes, edges)
          setNodes(laid.nodes)
          setEdges(laid.edges)
        } catch {
          setNodes(allNodes)
          setEdges(edges)
        }
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
    // Read nodes at call time to avoid closing over the array reference,
    // which changes on every position update and would cause this callback
    // (and downstream handleRun) to be recreated on every drag frame.
    const currentNodes = useStudioStore.getState().nodes
    if (currentNodes.length === 0) {
      applyStatus('error', 'Nothing to save — add some nodes first')
      return false
    }
    applyStatus('saving', 'Saving…')
    try {
      await Promise.all(
        currentNodes.map((node) => {
          const body = buildResourceBody(node, crewName)
          const plural =
            KIND_TO_PLURAL[capitalize(node.type ?? '')] ?? `${node.type ?? 'resource'}s`
          return api.post(`/api/v1/${plural}`, body)
        }),
      )

      // Synthesize and save the Crew resource
      const agentNodes = currentNodes.filter((n) => n.type === 'agent')
      const taskNodes = currentNodes.filter((n) => n.type === 'task')
      const agentRefs = agentNodes.map((n) => {
        const d = n.data
        const raw = (d['role'] as string | undefined) ?? (d['name'] as string | undefined) ?? n.id
        return `ref:agents/${toResourceName(raw)}`
      })
      const taskRefs = taskNodes.map((n) => {
        const d = n.data
        const raw = (d['name'] as string | undefined) ?? n.id
        return `ref:tasks/${toResourceName(raw)}`
      })
      const crewBody = {
        apiVersion: API_VERSION,
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
        `Saved ${currentNodes.length} resource${currentNodes.length !== 1 ? 's' : ''} + crew`,
      )
      return true
    } catch (err) {
      applyStatus('error', err instanceof Error ? err.message : 'Save failed')
      return false
    }
  }, [crewName, applyStatus, markClean])

  /* ── Run / Train / Test the crew (auto-saves first) ── */
  const handleRun = useCallback(
    async (params: RunParams) => {
      setRunDialogOpen(false)
      setExecutionId(null)

      // Auto-save before running
      const saved = await handleSave()
      if (!saved) return

      const modeLabel = params.mode === 'run' ? 'execution' : params.mode
      applyStatus('running', `Starting ${modeLabel}…`)
      try {
        let parsedInputs: Record<string, unknown> = {}
        try {
          parsedInputs = JSON.parse(params.inputs) as Record<string, unknown>
        } catch {
          // keep empty inputs
        }

        const slug = toResourceName(crewName)
        let result: { id: string }

        if (params.mode === 'train') {
          result = await api.post<{ id: string }>(`/api/v1/crews/${slug}/train`, {
            inputs: parsedInputs,
            n_iterations: params.iterations,
            filename: params.filename,
          })
        } else if (params.mode === 'test') {
          result = await api.post<{ id: string }>(`/api/v1/crews/${slug}/test`, {
            inputs: parsedInputs,
            n_iterations: params.iterations,
          })
        } else {
          result = await api.post<{ id: string }>(`/api/v1/crews/${slug}/kickoff`, {
            inputs: parsedInputs,
          })
        }

        setExecutionId(result.id)
        const successLabel =
          params.mode === 'train'
            ? 'Training started'
            : params.mode === 'test'
              ? 'Test started'
              : 'Execution started'
        applyStatus('success', `${successLabel} →`)
      } catch (err) {
        applyStatus('error', err instanceof Error ? err.message : `${modeLabel} failed`)
      }
    },
    [crewName, handleSave, applyStatus],
  )

  const handleLoadExample = useCallback(() => {
    const exampleNodes: Node[] = [
      {
        id: 'agent-researcher',
        type: 'agent',
        position: { x: 80, y: 60 },
        data: {
          role: 'Researcher',
          goal: 'List key facts about a topic',
          backstory: 'You find facts and list them. Be brief.',
        },
      },
      {
        id: 'agent-writer',
        type: 'agent',
        position: { x: 80, y: 260 },
        data: {
          role: 'Writer',
          goal: 'Write a short summary from given facts',
          backstory: 'You write clear, short summaries. Be brief.',
        },
      },
      {
        id: 'task-research',
        type: 'task',
        position: { x: 360, y: 60 },
        data: {
          name: 'research-topic',
          description: 'Write 3 key facts about {topic} in bullet point format.',
          expected_output: '3 bullet points about {topic}, each one sentence.',
          agent: 'ref:agents/researcher',
        },
      },
      {
        id: 'task-write',
        type: 'task',
        position: { x: 360, y: 260 },
        data: {
          name: 'write-report',
          description:
            'Using the research facts provided, write a 2-3 sentence summary about {topic}.',
          expected_output: 'A short summary about {topic} in 2-3 sentences.',
          agent: 'ref:agents/writer',
          context: ['ref:tasks/research-topic'],
        },
      },
    ]
    const exampleEdges: Edge[] = [
      {
        id: 'edge-researcher-research',
        source: 'agent-researcher',
        target: 'task-research',
        type: 'dataflow',
        markerEnd: DATAFLOW_MARKER_END,
      },
      {
        id: 'edge-writer-write',
        source: 'agent-writer',
        target: 'task-write',
        type: 'dataflow',
        markerEnd: DATAFLOW_MARKER_END,
      },
      {
        id: 'edge-research-write',
        source: 'task-research',
        target: 'task-write',
        type: 'dataflow',
        markerEnd: DATAFLOW_MARKER_END,
      },
    ]
    setNodes(exampleNodes)
    setEdges(exampleEdges)
    setCrewName('research-crew')
    markClean()
    applyStatus('success', 'Example crew loaded')
  }, [applyStatus, markClean, setEdges, setNodes])

  const handleAutoLayout = useCallback(async () => {
    const { nodes, edges } = useStudioStore.getState()
    if (nodes.length === 0) return
    setLayouting(true)
    try {
      const result = await autoLayout(nodes, edges)
      setNodes(result.nodes)
      setEdges(result.edges)
      applyStatus('success', 'Layout applied')
    } catch {
      applyStatus('error', 'Auto layout failed')
    } finally {
      setLayouting(false)
    }
  }, [applyStatus, setNodes, setEdges])

  return (
    <div className="flex h-full flex-col">
      <h1 className="sr-only">Studio</h1>
      <Toolbar
        crewName={crewName}
        onCrewNameChange={setCrewName}
        onSave={() => void handleSave()}
        onRunClick={() => setRunDialogOpen(true)}
        onLoadCrew={handleLoadCrew}
        onFetchCrews={() => void fetchCrews()}
        crews={crews}
        crewsLoading={crewsLoading}
        dirty={dirty}
        status={status}
        statusMessage={statusMessage}
        executionId={executionId}
        onNavigateToExecution={
          executionId ? () => void navigate(`/executions/${executionId}`) : undefined
        }
        canUndo={canUndo}
        canRedo={canRedo}
        undo={undo}
        redo={redo}
        yamlOpen={yamlOpen}
        onYamlToggle={() => setYamlOpen((v) => !v)}
        onAutoLayout={() => void handleAutoLayout()}
        layouting={layouting}
      />

      <div className="relative flex flex-1 overflow-hidden">
        <Palette />
        <Canvas onLoadExample={handleLoadExample} />
        {selectedNodeId && <PropertyPanel />}
        {yamlOpen && (
          <div className="w-[360px] shrink-0">
            <YamlEditor />
          </div>
        )}
      </div>
      <MobilePalette />

      <RunDialog
        open={runDialogOpen}
        onOpenChange={setRunDialogOpen}
        crewName={crewName}
        onRun={(params) => void handleRun(params)}
      />

      <ConfirmDialog
        open={!!pendingLoadCrew}
        onOpenChange={(open) => {
          if (!open) setPendingLoadCrew(null)
        }}
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
