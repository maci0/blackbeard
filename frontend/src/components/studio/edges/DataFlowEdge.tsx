import { memo, useMemo, useState } from 'react'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react'
import { cn } from '@/lib/utils'

const STYLE_DEFAULT = {
  stroke: '#94a3b8',
  strokeWidth: 1.5,
} as const

const STYLE_SELECTED = {
  stroke: '#6366f1',
  strokeWidth: 2.5,
} as const

const STYLE_RUNNING = {
  stroke: '#3b82f6',
  strokeWidth: 2,
} as const

const STYLE_SUCCESS = {
  stroke: '#10b981',
  strokeWidth: 2,
} as const

const STYLE_ERROR = {
  stroke: '#ef4444',
  strokeWidth: 2,
} as const

function getEdgeStyle(
  selected: boolean | undefined,
  execStatus: string | undefined,
): Record<string, unknown> {
  if (selected) return STYLE_SELECTED
  if (execStatus === 'error') return STYLE_ERROR
  if (execStatus === 'success') return STYLE_SUCCESS
  if (execStatus === 'running') return STYLE_RUNNING
  return STYLE_DEFAULT
}

export default memo(function DataFlowEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  selected,
  markerEnd,
  data,
}: EdgeProps) {
  const [showTooltip, setShowTooltip] = useState(false)

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  const execStatus = data?.['_execStatus'] as string | undefined
  const execOutput = data?.['_execOutput'] as string | undefined
  const execTokens = data?.['_execTokens'] as number | undefined
  const hasExecData = !!execOutput

  const style = getEdgeStyle(selected, execStatus)

  const labelStyle = useMemo(
    () => ({
      position: 'absolute' as const,
      transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
      pointerEvents: 'all' as const,
    }),
    [labelX, labelY],
  )

  const edgeClass = cn(
    selected && 'studio-edge-animated',
    execStatus === 'running' && 'studio-edge-dash',
  )

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={style}
        className={edgeClass || undefined}
      />

      <EdgeLabelRenderer>
        <div
          style={labelStyle}
          className={cn(
            hasExecData && 'cursor-pointer',
            'rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
          )}
          onClick={() => hasExecData && setShowTooltip((v) => !v)}
          onKeyDown={(e) => {
            if ((e.key === 'Enter' || e.key === ' ') && hasExecData) setShowTooltip((v) => !v)
          }}
          role={hasExecData ? 'button' : undefined}
          tabIndex={hasExecData ? 0 : undefined}
          aria-label={hasExecData ? 'Show wire data' : undefined}
        >
          {/* Label badge */}
          {typeof data?.label === 'string' && (
            <div className="rounded-full border border-border bg-card px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-muted-foreground shadow-sm">
              {data.label}
            </div>
          )}

          {/* Execution status dot */}
          {execStatus && !data?.label && (
            <div
              className={cn(
                'h-2 w-2 rounded-full',
                execStatus === 'success' && 'bg-emerald-500',
                execStatus === 'error' && 'bg-red-500',
                execStatus === 'running' && 'animate-pulse bg-blue-500 motion-reduce:animate-none',
              )}
              title={`Status: ${execStatus}`}
            />
          )}

          {/* Token count badge */}
          {execTokens != null && execTokens > 0 && (
            <div className="mt-0.5 rounded bg-muted/80 px-1 py-px text-[8px] text-muted-foreground">
              {execTokens.toLocaleString()} tok
            </div>
          )}

          {/* Expanded data tooltip */}
          {showTooltip && execOutput && (
            <div className="mt-1 max-w-[300px] rounded-lg border bg-card p-2 shadow-lg">
              <p className="mb-1 text-[9px] font-semibold text-muted-foreground">Wire Data</p>
              <pre className="max-h-[150px] overflow-auto whitespace-pre-wrap font-mono text-[10px] text-foreground/80">
                {execOutput.length > 500 ? `${execOutput.slice(0, 500)}…` : execOutput}
              </pre>
              {execOutput.length > 500 && (
                <p className="mt-1 text-[8px] text-muted-foreground">
                  {execOutput.length.toLocaleString()} chars total
                </p>
              )}
            </div>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  )
})
