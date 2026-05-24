import { useState, useCallback, useEffect, useRef, useMemo } from 'react'
import { ReactFlowProvider } from '@xyflow/react'
import { useNavigate } from 'react-router-dom'
import { useShallow } from 'zustand/react/shallow'
import { useStudioStore } from '@/stores/studioStore'
import { api } from '@/api/client'
import { capitalize, toResourceName, parseRef, getErrorMessage } from '@/lib/utils'
import { useCollaboration, useDocumentTitle } from '@/hooks'
import { API_VERSION, KIND_TO_PLURAL } from '@/lib/kinds'
import { DATAFLOW_MARKER_END } from '@/components/studio/defaults'
import Palette, { MobilePalette } from '@/components/studio/Palette'
import Canvas from '@/components/studio/Canvas'
import PropertyPanel from '@/components/studio/PropertyPanel'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import type { RunStatus } from '@/lib/types'
import { RunDialog, type RunParams } from '@/components/studio/RunDialog'
import { Toolbar } from '@/components/studio/Toolbar'
import { CopilotDialog, type CopilotResource } from '@/components/studio/CopilotDialog'
import { CursorOverlay } from '@/components/studio/CursorOverlay'
import { YamlEditor } from '@/components/studio/YamlEditor'
import { autoLayout } from '@/components/studio/autoLayout'
import type { Node, Edge } from '@xyflow/react'
import type { Resource } from '@/lib/types'

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

/** Padding around child nodes inside a crew group container. */
const GROUP_PADDING = { top: 40, right: 20, bottom: 20, left: 20 }

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
/* Build a Flow resource body from flowStep nodes + edges              */
/* ------------------------------------------------------------------ */

function buildFlowBody(flowName: string, flowStepNodes: Node[], edges: Edge[]) {
  const steps = flowStepNodes.map((node) => {
    const data = node.data
    const stepName = (data['name'] as string | undefined) ?? ''
    const stepType = (data['type'] as string | undefined) ?? 'crew'
    const listenTo = (data['listen_to'] as string[] | undefined) ?? []

    // Derive listen_to from edges too — incoming edges imply dependency
    const edgeListenTo = edges
      .filter((e) => e.target === node.id)
      .map((e) => {
        const src = flowStepNodes.find((n) => n.id === e.source)
        return src ? ((src.data['name'] as string | undefined) ?? '') : ''
      })
      .filter(Boolean)

    const allListenTo = [...new Set([...listenTo, ...edgeListenTo])]

    const step: Record<string, unknown> = {
      name: stepName,
      type: stepType,
    }

    if (stepType === 'crew' && data['crew']) {
      step.crew = data['crew']
    }
    if (stepType === 'function' && data['function_path']) {
      step.function_path = data['function_path']
    }
    if (allListenTo.length > 0) {
      step.listen_to = allListenTo
    }

    return step
  })

  return {
    apiVersion: API_VERSION,
    kind: 'Flow',
    metadata: { name: toResourceName(flowName) },
    spec: { steps },
  }
}

/* ------------------------------------------------------------------ */
/* Build crew group node to encompass child nodes                      */
/* ------------------------------------------------------------------ */

function buildCrewGroupNode(crewName: string, childNodes: Node[]): Node {
  let minX = Infinity
  let minY = Infinity
  let maxX = -Infinity
  let maxY = -Infinity

  const nodeWidth = 120
  const nodeHeight = 120

  for (const n of childNodes) {
    minX = Math.min(minX, n.position.x)
    minY = Math.min(minY, n.position.y)
    maxX = Math.max(maxX, n.position.x + nodeWidth)
    maxY = Math.max(maxY, n.position.y + nodeHeight)
  }

  return {
    id: `crewGroup-${crewName}`,
    type: 'crewGroup',
    position: {
      x: minX - GROUP_PADDING.left,
      y: minY - GROUP_PADDING.top,
    },
    data: { name: crewName },
    style: {
      width: maxX - minX + GROUP_PADDING.left + GROUP_PADDING.right,
      height: maxY - minY + GROUP_PADDING.top + GROUP_PADDING.bottom,
    },
    // Group nodes should render behind child nodes
    zIndex: -1,
  }
}

/* ------------------------------------------------------------------ */
/* Studio inner — uses the ReactFlowProvider context from parent       */
/* ------------------------------------------------------------------ */

function StudioInner() {
  const navigate = useNavigate()
  const [runDialogOpen, setRunDialogOpen] = useState(false)
  const [status, setStatus] = useState<RunStatus>('idle')
  const [statusMessage, setStatusMessage] = useState('')
  const [executionId, setExecutionId] = useState<string | null>(null)
  const [crews, setCrews] = useState<string[]>([])
  const [crewsLoading, setCrewsLoading] = useState(false)
  const [pendingLoadCrew, setPendingLoadCrew] = useState<string | null>(null)
  const [yamlOpen, setYamlOpen] = useState(false)
  const [layouting, setLayouting] = useState(false)
  const [copilotOpen, setCopilotOpen] = useState(false)
  const [collabEnabled, setCollabEnabled] = useState(false)

  const statusTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const {
    crewName,
    setCrewName,
    selectedNodeId,
    setNodes,
    setEdges,
    markClean,
    dirty,
    canUndo,
    canRedo,
    undo,
    redo,
  } = useStudioStore(
    useShallow((s) => ({
      crewName: s.crewName,
      setCrewName: s.setCrewName,
      selectedNodeId: s.selectedNodeId,
      setNodes: s.setNodes,
      setEdges: s.setEdges,
      markClean: s.markClean,
      dirty: s.dirty,
      canUndo: s.canUndo,
      canRedo: s.canRedo,
      undo: s.undo,
      redo: s.redo,
    })),
  )

  const {
    participants: collabParticipants,
    connected: collabConnected,
    broadcast,
    broadcastCursor,
    remoteCursors,
  } = useCollaboration(crewName, collabEnabled)

  useDocumentTitle('Studio')

  const lastCursorBroadcast = useRef(0)
  const throttledBroadcastCursor = useMemo(() => {
    if (!broadcastCursor) return undefined
    const CURSOR_THROTTLE_MS = 33 // ~30fps
    return (e: React.MouseEvent) => {
      const now = performance.now()
      if (now - lastCursorBroadcast.current < CURSOR_THROTTLE_MS) return
      lastCursorBroadcast.current = now
      broadcastCursor({ x: e.clientX, y: e.clientY, userId: 'self', name: 'You' })
    }
  }, [broadcastCursor])

  /* ── Broadcast canvas changes to collaborators ── */
  useEffect(() => {
    if (!collabEnabled || !collabConnected) return

    // Subscribe to Zustand store changes and broadcast relevant operations.
    // The useCollaboration hook sets applyingRemoteRef=true when applying
    // incoming changes, which causes broadcast() to no-op and prevents
    // echo loops.
    //
    // Build lookup Sets lazily and only for the diff direction needed,
    // so the common case (node move = same array length) pays O(n) not O(2n).
    const unsubscribe = useStudioStore.subscribe((state, prevState) => {
      if (state.nodes !== prevState.nodes) {
        if (state.nodes.length > prevState.nodes.length) {
          const prevIds = new Set(prevState.nodes.map((n) => n.id))
          for (const node of state.nodes) {
            if (!prevIds.has(node.id)) broadcast('node_add', { ...node })
          }
        } else if (state.nodes.length < prevState.nodes.length) {
          const currentIds = new Set(state.nodes.map((n) => n.id))
          for (const node of prevState.nodes) {
            if (!currentIds.has(node.id)) broadcast('node_delete', { id: node.id })
          }
        } else {
          // Same count — compare by index reference (fast path for the
          // common drag case where applyNodeChanges preserves array order
          // and only replaces the dragged node object).
          for (let i = 0; i < state.nodes.length; i++) {
            const curr = state.nodes[i]!
            const prev = prevState.nodes[i]
            if (curr === prev) continue
            if (
              prev &&
              curr.id === prev.id &&
              (curr.position.x !== prev.position.x || curr.position.y !== prev.position.y)
            ) {
              broadcast('node_move', { id: curr.id, position: curr.position })
            }
          }
        }
      }

      if (state.edges !== prevState.edges) {
        if (state.edges.length > prevState.edges.length) {
          const prevIds = new Set(prevState.edges.map((e) => e.id))
          for (const edge of state.edges) {
            if (!prevIds.has(edge.id)) broadcast('edge_add', { ...edge })
          }
        } else if (state.edges.length < prevState.edges.length) {
          const currentIds = new Set(state.edges.map((e) => e.id))
          for (const edge of prevState.edges) {
            if (!currentIds.has(edge.id)) broadcast('edge_delete', { id: edge.id })
          }
        }
      }
    })
    return unsubscribe
  }, [collabEnabled, collabConnected, broadcast])

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

        const childNodes = [...agentNodes, ...taskNodes]
        let allNodes: Node[]
        try {
          const laid = await autoLayout(childNodes, edges)
          // Build crew group from laid-out positions
          const groupNode = buildCrewGroupNode(crew.metadata.name, laid.nodes)
          // Set parentId on child nodes so they are visually contained
          const parented = laid.nodes.map((n) => ({
            ...n,
            parentId: groupNode.id,
            extent: 'parent' as const,
            position: {
              x: n.position.x - groupNode.position.x,
              y: n.position.y - groupNode.position.y,
            },
          }))
          allNodes = [groupNode, ...parented]
          setNodes(allNodes)
          setEdges(laid.edges)
        } catch {
          const groupNode = buildCrewGroupNode(crew.metadata.name, childNodes)
          const parented = childNodes.map((n) => ({
            ...n,
            parentId: groupNode.id,
            extent: 'parent' as const,
            position: {
              x: n.position.x - groupNode.position.x,
              y: n.position.y - groupNode.position.y,
            },
          }))
          allNodes = [groupNode, ...parented]
          setNodes(allNodes)
          setEdges(edges)
        }
        setCrewName(crew.metadata.name)
        markClean()
        applyStatus('success', `Loaded "${name}"`)
      } catch (err) {
        applyStatus('error', getErrorMessage(err, 'Load failed'))
      }
    },
    [applyStatus, markClean, setCrewName, setEdges, setNodes],
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
    const { nodes: currentNodes, edges: currentEdges } = useStudioStore.getState()
    if (currentNodes.length === 0) {
      applyStatus('error', 'Nothing to save — add some nodes first')
      return false
    }
    applyStatus('saving', 'Saving…')

    const flowStepNodes = currentNodes.filter((n) => n.type === 'flowStep')
    const isFlowMode = flowStepNodes.length > 0

    try {
      // Save individual resource nodes (agent, task, tool — skip crewGroup and flowStep)
      const resourceNodes = currentNodes.filter(
        (n) => n.type === 'agent' || n.type === 'task' || n.type === 'tool',
      )

      // Save PII nodes as Guardrail resources
      const piiNodes = currentNodes.filter((n) => n.type === 'pii')

      await Promise.all([
        ...resourceNodes.map((node) => {
          const body = buildResourceBody(node, crewName)
          const plural =
            KIND_TO_PLURAL[capitalize(node.type ?? '')] ?? `${node.type ?? 'resource'}s`
          return api.post(`/api/v1/${plural}`, body)
        }),
        ...piiNodes.map((node) => {
          const data = node.data
          const rawName = (data['name'] as string | undefined) ?? node.id
          // eslint-disable-next-line @typescript-eslint/no-unused-vars
          const { name: _unused, ...rest } = data
          const spec: Record<string, unknown> = {
            type: 'pii',
            ...rest,
          }
          // Remap canvas data keys to Guardrail spec keys
          if (spec['entities'] !== undefined) {
            spec['pii_entities'] = spec['entities']
            delete spec['entities']
          }
          if (spec['action'] !== undefined) {
            spec['pii_action'] = spec['action']
            delete spec['action']
          }
          const body = {
            apiVersion: API_VERSION,
            kind: 'Guardrail',
            metadata: {
              name: toResourceName(rawName),
              labels: { crew: crewName },
            },
            spec,
          }
          return api.post('/api/v1/guardrails', body)
        }),
      ])

      const totalSaved = resourceNodes.length + piiNodes.length

      if (isFlowMode) {
        // Save as a Flow resource
        const flowBody = buildFlowBody(crewName, flowStepNodes, currentEdges)
        await api.post('/api/v1/flows', flowBody)

        markClean()
        applyStatus('success', `Saved ${totalSaved} resource${totalSaved !== 1 ? 's' : ''} + flow`)
      } else {
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
        applyStatus('success', `Saved ${totalSaved} resource${totalSaved !== 1 ? 's' : ''} + crew`)
      }
      return true
    } catch (err) {
      applyStatus('error', getErrorMessage(err, 'Save failed'))
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
        if (params.inputs.trim()) {
          try {
            parsedInputs = JSON.parse(params.inputs) as Record<string, unknown>
          } catch {
            applyStatus('error', 'Invalid JSON in run inputs')
            return
          }
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
        applyStatus('error', getErrorMessage(err, `${modeLabel} failed`))
      }
    },
    [crewName, handleSave, applyStatus],
  )

  const handleLoadExample = useCallback(() => {
    const childNodes: Node[] = [
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

    // Wrap child nodes in a crew group
    const groupNode = buildCrewGroupNode('research-crew', childNodes)
    const parentedNodes = childNodes.map((n) => ({
      ...n,
      parentId: groupNode.id,
      extent: 'parent' as const,
      position: {
        x: n.position.x - groupNode.position.x,
        y: n.position.y - groupNode.position.y,
      },
    }))

    setNodes([groupNode, ...parentedNodes])
    setEdges(exampleEdges)
    setCrewName('research-crew')
    markClean()
    applyStatus('success', 'Example crew loaded')
  }, [applyStatus, markClean, setCrewName, setEdges, setNodes])

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

  /* ── Apply copilot-generated resources to the canvas ── */
  const handleCopilotApply = useCallback(
    (resources: CopilotResource[]) => {
      const agentResources = resources.filter((r) => r.kind === 'Agent')
      const taskResources = resources.filter((r) => r.kind === 'Task')
      const crewResource = resources.find((r) => r.kind === 'Crew')

      // Build nodes — agents on left, tasks on right
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

      // Build edges: task.spec.agent ref -> agent node
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

      // Add context edges between tasks
      for (const task of taskResources) {
        const contextRefs = (task.spec.context as string[] | undefined) ?? []
        for (const ctxRef of contextRefs) {
          const ctxName = parseRef(ctxRef)
          edges.push({
            id: `edge-ctx-${ctxName}-${task.metadata.name}`,
            source: `task-${ctxName}`,
            target: `task-${task.metadata.name}`,
            type: 'dataflow',
            markerEnd: DATAFLOW_MARKER_END,
          })
        }
      }

      const childNodes = [...agentNodes, ...taskNodes]
      const groupName = crewResource?.metadata.name ?? toResourceName(crewName)

      // Wrap in a crew group node
      const groupNode = buildCrewGroupNode(groupName, childNodes)
      const parentedNodes = childNodes.map((n) => ({
        ...n,
        parentId: groupNode.id,
        extent: 'parent' as const,
        position: {
          x: n.position.x - groupNode.position.x,
          y: n.position.y - groupNode.position.y,
        },
      }))

      setNodes([groupNode, ...parentedNodes])
      setEdges(edges)

      if (crewResource?.metadata.name) {
        setCrewName(crewResource.metadata.name)
      }

      applyStatus('success', `Copilot generated ${resources.length} resources`)
    },
    [applyStatus, crewName, setCrewName, setEdges, setNodes],
  )

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
        onCopilotClick={() => setCopilotOpen(true)}
        onAutoLayout={() => void handleAutoLayout()}
        layouting={layouting}
        collabEnabled={collabEnabled}
        onCollabToggle={() => setCollabEnabled((v) => !v)}
        collabConnected={collabConnected}
        collabParticipants={collabParticipants}
      />

      <div
        className="relative flex flex-1 overflow-hidden"
        onMouseMove={collabEnabled && collabConnected ? throttledBroadcastCursor : undefined}
      >
        <Palette />
        <Canvas onLoadExample={handleLoadExample} />
        {collabEnabled && collabConnected && (
          <CursorOverlay cursors={Array.from(remoteCursors.values())} />
        )}
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

      <CopilotDialog
        open={copilotOpen}
        onOpenChange={setCopilotOpen}
        onApply={handleCopilotApply}
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
