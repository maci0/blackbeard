import { BaseEdge, getBezierPath, type EdgeProps } from '@xyflow/react'

export default function ToolAssignEdge({
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
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: '#cbd5e1',
          strokeWidth: 1.5,
          strokeDasharray: '5 4',
        }}
      />
      {/* Source dot */}
      <circle cx={sourceX} cy={sourceY} r={3} fill="#94a3b8" />
      {/* Target dot */}
      <circle cx={targetX} cy={targetY} r={3} fill="#94a3b8" />
    </>
  )
}
