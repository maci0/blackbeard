import { memo } from 'react'
import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from '@xyflow/react'

const STYLE_DEFAULT = {
  stroke: '#94a3b8',
  strokeWidth: 1.5,
} as const

const STYLE_SELECTED = {
  stroke: '#6366f1',
  strokeWidth: 2.5,
} as const

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
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={selected ? STYLE_SELECTED : STYLE_DEFAULT}
        className={selected ? 'studio-edge-animated' : undefined}
      />

      {data?.label && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              pointerEvents: 'none',
            }}
            className="rounded-full border border-border bg-card px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-muted-foreground shadow-sm"
          >
            {typeof data.label === 'string' ? data.label : JSON.stringify(data.label)}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  )
})
