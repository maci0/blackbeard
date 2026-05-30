import { ChevronRight } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { useShallow } from 'zustand/react/shallow'

export function CanvasBreadcrumb() {
  const { navStack, crewName, popNav } = useStudioStore(
    useShallow((s) => ({
      navStack: s.navStack,
      crewName: s.crewName,
      popNav: s.popNav,
    })),
  )

  if (navStack.length === 0) return null

  const crumbs = [...navStack.map((e) => e.crewName), crewName]

  return (
    <nav
      aria-label="Canvas navigation"
      className="flex shrink-0 items-center gap-1 border-b bg-muted/30 px-3 py-1 text-xs"
    >
      {crumbs.map((name, i) => {
        const isLast = i === crumbs.length - 1
        const depth = navStack.length - i
        return (
          <span key={i} className="flex items-center gap-1">
            {i > 0 && <ChevronRight className="h-3 w-3 text-muted-foreground/50" />}
            {isLast ? (
              <span className="font-medium text-foreground">{name}</span>
            ) : (
              <button
                type="button"
                onClick={() => {
                  for (let d = 0; d < depth; d++) popNav()
                }}
                className="text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
              >
                {name}
              </button>
            )}
          </span>
        )
      })}
    </nav>
  )
}
