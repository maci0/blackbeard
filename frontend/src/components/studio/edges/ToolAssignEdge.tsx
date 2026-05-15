import { memo } from 'react'
import { BaseEdge, getBezierPath, type EdgeProps } from '@xyflow/react'

const EDGE_STYLE = {
  stroke: '#94a3b8',
  strokeWidth: 1.5,
  strokeDasharray: '5 4',
} as const

export default memo(function ToolAssignEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
}: EdgeProps) {
  const [edgePath] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  })

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={EDGE_STYLE} />
      <circle cx={sourceX} cy={sourceY} r={3} fill="#94a3b8" aria-hidden="true" />
      <circle cx={targetX} cy={targetY} r={3} fill="#94a3b8" aria-hidden="true" />
    </>
  )
})
