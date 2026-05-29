import { useState, useEffect, useId, useMemo } from 'react'
import { useBlackbeard } from './BlackbeardProvider'
import { apiFetch } from './fetch'
import type { Resource } from './types'

export interface CrewViewerProps {
  /** Name of the crew resource to visualize. */
  crewName: string
  /** Namespace containing the crew (defaults to "default"). */
  namespace?: string
}

/* ------------------------------------------------------------------ */
/* Helpers                                                             */
/* ------------------------------------------------------------------ */

/** Parse "ref:agents/researcher" into "researcher". */
function parseRef(ref: string): string {
  if (ref.startsWith('ref:')) {
    const parts = ref.slice(4).split('/')
    return parts[parts.length - 1] ?? ref
  }
  return ref
}

const NODE_COLORS: Record<string, { bg: string; border: string; text: string }> = {
  agent: { bg: '#f5f3ff', border: '#8b5cf6', text: '#5b21b6' },
  task: { bg: '#eff6ff', border: '#3b82f6', text: '#1e40af' },
}

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

/**
 * Read-only crew visualization component. Fetches the crew, its agents,
 * and its tasks from the API, then renders a simple node graph using
 * plain divs and SVG lines. No React Flow dependency.
 */
export function CrewViewer({ crewName, namespace }: CrewViewerProps) {
  const config = useBlackbeard()
  const markerId = `bb-arrow-${useId().replace(/:/g, '')}`
  const [agents, setAgents] = useState<Resource[]>([])
  const [tasks, setTasks] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true

    async function load() {
      setLoading(true)
      setError(null)
      try {
        const ns = namespace ?? 'default'
        const nsParam = `project=${encodeURIComponent(ns)}`
        const crew = await apiFetch<Resource>(config, `/api/v1/crews/${encodeURIComponent(crewName)}?${nsParam}`)
        const agentNames = ((crew.spec.agents as string[] | undefined) ?? []).map(parseRef)
        const taskNames = ((crew.spec.tasks as string[] | undefined) ?? []).map(parseRef)

        const [agentResults, taskResults] = await Promise.all([
          Promise.all(agentNames.map((n) => apiFetch<Resource>(config, `/api/v1/agents/${encodeURIComponent(n)}?${nsParam}`))),
          Promise.all(taskNames.map((n) => apiFetch<Resource>(config, `/api/v1/tasks/${encodeURIComponent(n)}?${nsParam}`))),
        ])

        if (!active) return
        setAgents(agentResults)
        setTasks(taskResults)
      } catch (err) {
        if (!active) return
        setError(err instanceof Error ? err.message : 'Failed to load crew')
      } finally {
        if (active) setLoading(false)
      }
    }

    void load()
    return () => {
      active = false
    }
  }, [config, crewName, namespace])

  /* ── Compute layout positions ── */
  const NODE_W = 180
  const NODE_H = 72
  const COL_GAP = 120
  const ROW_GAP = 24
  const PAD = 24

  const agentX = PAD
  const taskX = PAD + NODE_W + COL_GAP

  /** Build edges: task.spec.agent ref -> agent node. */
  const edges = useMemo(() => {
    const result: { fromIdx: number; toIdx: number }[] = []
    tasks.forEach((task, tIdx) => {
      const agentRef = task.spec.agent as string | undefined
      if (!agentRef) return
      const agentName = parseRef(agentRef)
      const aIdx = agents.findIndex((a) => a.metadata.name === agentName)
      if (aIdx >= 0) {
        result.push({ fromIdx: aIdx, toIdx: tIdx })
      }
    })
    return result
  }, [agents, tasks])

  const maxRows = Math.max(agents.length, tasks.length, 1)
  const svgWidth = taskX + NODE_W + PAD
  const svgHeight = PAD + maxRows * (NODE_H + ROW_GAP)

  /* ── Render ── */

  if (loading) {
    return (
      <div style={containerStyle}>
        <span style={{ color: '#6b7280', fontSize: 13 }}>Loading crew...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div style={containerStyle}>
        <span style={{ color: '#ef4444', fontSize: 13 }}>{error}</span>
      </div>
    )
  }

  if (agents.length === 0 && tasks.length === 0) {
    return (
      <div style={containerStyle}>
        <span style={{ color: '#6b7280', fontSize: 13 }}>
          Crew "{crewName}" has no agents or tasks.
        </span>
      </div>
    )
  }

  return (
    <div style={containerStyle}>
      {/* Header */}
      <div style={{ marginBottom: 12, fontWeight: 600, fontSize: 14, color: '#111827' }}>
        {crewName}
      </div>

      {/* Graph */}
      <div style={{ position: 'relative', width: svgWidth, height: svgHeight }}>
        {/* SVG edges */}
        <svg
          width={svgWidth}
          height={svgHeight}
          style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
        >
          <defs>
            <marker
              id={markerId}
              markerWidth="8"
              markerHeight="6"
              refX="8"
              refY="3"
              orient="auto"
            >
              <polygon points="0 0, 8 3, 0 6" fill="#94a3b8" />
            </marker>
          </defs>
          {edges.map(({ fromIdx, toIdx }, i) => {
            const x1 = agentX + NODE_W
            const y1 = PAD + fromIdx * (NODE_H + ROW_GAP) + NODE_H / 2
            const x2 = taskX
            const y2 = PAD + toIdx * (NODE_H + ROW_GAP) + NODE_H / 2
            return (
              <line
                key={i}
                x1={x1}
                y1={y1}
                x2={x2}
                y2={y2}
                stroke="#94a3b8"
                strokeWidth={1.5}
                markerEnd={`url(#${markerId})`}
              />
            )
          })}
        </svg>

        {/* Agent nodes */}
        {agents.map((agent, i) => (
          <div
            key={agent.id ?? agent.metadata.name}
            style={{
              ...nodeStyle,
              ...nodeStyleForKind('agent'),
              left: agentX,
              top: PAD + i * (NODE_H + ROW_GAP),
              width: NODE_W,
              height: NODE_H,
            }}
          >
            <div style={{ fontSize: 10, textTransform: 'uppercase', opacity: 0.6, marginBottom: 2 }}>
              Agent
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.3 }}>
              {(agent.spec.role as string | undefined) ?? agent.metadata.name}
            </div>
          </div>
        ))}

        {/* Task nodes */}
        {tasks.map((task, i) => (
          <div
            key={task.id ?? task.metadata.name}
            style={{
              ...nodeStyle,
              ...nodeStyleForKind('task'),
              left: taskX,
              top: PAD + i * (NODE_H + ROW_GAP),
              width: NODE_W,
              height: NODE_H,
            }}
          >
            <div style={{ fontSize: 10, textTransform: 'uppercase', opacity: 0.6, marginBottom: 2 }}>
              Task
            </div>
            <div style={{ fontWeight: 600, fontSize: 13, lineHeight: 1.3 }}>
              {task.metadata.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Styles                                                              */
/* ------------------------------------------------------------------ */

const containerStyle: React.CSSProperties = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
  padding: 16,
  borderRadius: 8,
  border: '1px solid #e5e7eb',
  backgroundColor: '#fff',
  overflow: 'auto',
}

const nodeStyle: React.CSSProperties = {
  position: 'absolute',
  borderRadius: 8,
  padding: '10px 12px',
  boxSizing: 'border-box',
  overflow: 'hidden',
}

function nodeStyleForKind(kind: string): React.CSSProperties {
  const colors = NODE_COLORS[kind] ?? { bg: '#f9fafb', border: '#d1d5db', text: '#374151' }
  return {
    backgroundColor: colors.bg,
    border: `1.5px solid ${colors.border}`,
    color: colors.text,
  }
}
