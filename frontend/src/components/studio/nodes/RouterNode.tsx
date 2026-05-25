import { memo } from 'react'
import { type NodeProps } from '@xyflow/react'
import { Route } from 'lucide-react'
import { NodeShell } from './NodeShell'

export default memo(function RouterNode({ data, selected }: NodeProps) {
  const name = data['name'] as string | undefined
  const routes = data['routes'] as Record<string, string> | undefined
  const routeCount = routes ? Object.keys(routes).length : 0

  return (
    <NodeShell
      color="cyan"
      icon={Route}
      label="Router"
      ariaLabel={`Router: ${name || 'Unnamed Router'}`}
      selected={!!selected}
      width="w-[160px]"
    >
      <p
        className="truncate text-xs font-semibold leading-tight text-foreground"
        title={name || 'Unnamed Router'}
      >
        {name || 'Unnamed Router'}
      </p>

      <div className="pt-0.5">
        <span className="inline-flex items-center rounded border border-cyan-100 bg-cyan-50 px-1 py-px text-[10px] font-semibold text-cyan-700 dark:border-cyan-800 dark:bg-cyan-950 dark:text-cyan-300">
          {routeCount} route{routeCount !== 1 ? 's' : ''}
        </span>
      </div>

      {routes && routeCount > 0 ? (
        <div className="flex flex-wrap gap-0.5 pt-0.5">
          {Object.entries(routes)
            .slice(0, 3)
            .map(([condition, target]) => (
              <span
                key={condition}
                className="inline-flex items-center rounded border border-cyan-100 bg-cyan-50 px-1 py-px text-[9px] font-medium text-cyan-600 dark:border-cyan-800 dark:bg-cyan-950 dark:text-cyan-400"
                title={`${condition} -> ${target}`}
              >
                {condition.slice(0, 8)}
              </span>
            ))}
          {routeCount > 3 && (
            <span
              className="inline-flex items-center rounded border border-slate-100 bg-slate-50 px-1 py-px text-[9px] font-medium text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400"
              title={Object.keys(routes).slice(3).join(', ')}
            >
              +{routeCount - 3}
            </span>
          )}
        </div>
      ) : (
        <p className="text-[10px] italic text-muted-foreground/60">No routes defined</p>
      )}
    </NodeShell>
  )
})
