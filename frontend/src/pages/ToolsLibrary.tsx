import { useEffect, useState, useMemo } from 'react'
import {
  Search,
  Download,
  Check,
  Globe,
  Database,
  Code,
  MessageSquare,
  FileText,
  Sparkles,
  Loader2,
  RefreshCw,
} from 'lucide-react'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { ErrorAlert } from '@/components/ui/ErrorAlert'
import { CardSkeleton } from '@/components/ui/Skeleton'
import { cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks'
import { useToastStore } from '@/stores/toastStore'

interface LibraryTool {
  slug: string
  name: string
  description: string
  category: string
  type: string
  class_path: string
  sandbox: string
  tags: string[]
}

interface LibraryResponse {
  tools: LibraryTool[]
  total: number
  categories: string[]
}

const CATEGORY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  web: Globe,
  data: Database,
  code: Code,
  communication: MessageSquare,
  file: FileText,
  ai: Sparkles,
}

const CATEGORY_COLORS: Record<string, string> = {
  web: 'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900 dark:text-blue-300',
  data: 'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900 dark:text-emerald-300',
  code: 'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900 dark:text-violet-300',
  communication:
    'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900 dark:text-amber-300',
  file: 'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-800 dark:text-slate-300',
  ai: 'bg-pink-100 text-pink-700 border-pink-200 dark:bg-pink-900 dark:text-pink-300',
}

function CategoryBadge({ category }: { category: string }) {
  const Icon = CATEGORY_ICONS[category] ?? Code
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-semibold',
        CATEGORY_COLORS[category] ?? CATEGORY_COLORS.code,
      )}
    >
      <Icon className="h-2.5 w-2.5" />
      {category}
    </span>
  )
}

function TypeBadge({ type }: { type: string }) {
  const colors: Record<string, string> = {
    python: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
    mcp: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
    wasm: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  }
  return (
    <span
      className={cn(
        'rounded px-1.5 py-0.5 text-[9px] font-semibold',
        colors[type] ?? 'bg-gray-100 text-gray-600',
      )}
    >
      {type}
    </span>
  )
}

export default function ToolsLibrary() {
  useDocumentTitle('Tools Library')

  const [tools, setTools] = useState<LibraryTool[]>([])
  const [categories, setCategories] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [filter, setFilter] = useState('')
  const [activeCategory, setActiveCategory] = useState<string | null>(null)
  const [installing, setInstalling] = useState<Set<string>>(new Set())
  const [installed, setInstalled] = useState<Set<string>>(new Set())
  const toasts = useToastStore()

  const fetchLibrary = async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (activeCategory) params.set('category', activeCategory)
      if (filter) params.set('search', filter)
      const resp = await api.get<LibraryResponse>(
        `/api/v1/tools/library${params.toString() ? `?${params}` : ''}`,
      )
      setTools(resp.tools)
      setCategories(resp.categories)
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load tools library'))
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void fetchLibrary()
  }, [activeCategory]) // eslint-disable-line react-hooks/exhaustive-deps

  const filtered = useMemo(() => {
    if (!filter) return tools
    const q = filter.toLowerCase()
    return tools.filter(
      (t) =>
        t.name.toLowerCase().includes(q) ||
        t.description.toLowerCase().includes(q) ||
        t.tags.some((tag) => tag.includes(q)),
    )
  }, [tools, filter])

  const handleInstall = async (slug: string) => {
    setInstalling((prev) => new Set(prev).add(slug))
    try {
      await api.post('/api/v1/tools/library/install', { slugs: [slug] })
      setInstalled((prev) => new Set(prev).add(slug))
      toasts.success(`Tool "${slug}" installed`)
    } catch (err) {
      toasts.error(getErrorMessage(err, `Failed to install ${slug}`))
    } finally {
      setInstalling((prev) => {
        const next = new Set(prev)
        next.delete(slug)
        return next
      })
    }
  }

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-6xl p-6">
        <PageHeader
          title="Tools Library"
          description="Browse and install curated tools for your agents"
          actions={
            <button
              type="button"
              onClick={() => void fetchLibrary()}
              disabled={loading}
              aria-label="Refresh library"
              className="flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
            </button>
          }
        />

        {/* Search + category chips */}
        <div className="mt-6 space-y-3">
          <div className="relative max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              type="text"
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              placeholder="Search tools…"
              aria-label="Search tools library"
              className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveCategory(null)}
              className={cn(
                'rounded-full border px-3 py-1 text-xs font-medium transition-colors',
                activeCategory === null
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-muted-foreground hover:text-foreground',
              )}
            >
              All
            </button>
            {categories.map((cat) => (
              <button
                key={cat}
                type="button"
                onClick={() => setActiveCategory(cat === activeCategory ? null : cat)}
                className={cn(
                  'rounded-full border px-3 py-1 text-xs font-medium capitalize transition-colors',
                  cat === activeCategory
                    ? 'border-primary bg-primary/10 text-primary'
                    : 'border-border text-muted-foreground hover:text-foreground',
                )}
              >
                {cat}
              </button>
            ))}
          </div>
        </div>

        {/* Content */}
        <div className="mt-6">
          {error && (
            <ErrorAlert
              message={error}
              onAction={() => void fetchLibrary()}
              actionLabel="Retry"
              onDismiss={() => setError(null)}
              className="mb-4"
            />
          )}

          {loading ? (
            <CardSkeleton count={6} />
          ) : filtered.length === 0 ? (
            <p className="py-12 text-center text-sm text-muted-foreground">
              No tools match your search.
            </p>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filtered.map((tool) => {
                const isInstalling = installing.has(tool.slug)
                const isInstalled = installed.has(tool.slug)

                return (
                  <div
                    key={tool.slug}
                    className="overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-150 hover:shadow-md"
                  >
                    <div className="flex items-start justify-between border-b bg-muted/20 px-4 pb-3 pt-4">
                      <div className="min-w-0 flex-1">
                        <h3 className="text-sm font-semibold">{tool.name}</h3>
                        <div className="mt-1 flex items-center gap-1.5">
                          <CategoryBadge category={tool.category} />
                          <TypeBadge type={tool.type} />
                        </div>
                      </div>
                    </div>

                    <div className="px-4 py-3">
                      <p className="line-clamp-2 text-xs text-muted-foreground">
                        {tool.description}
                      </p>
                      {tool.tags.length > 0 && (
                        <div className="mt-2 flex flex-wrap gap-1">
                          {tool.tags.slice(0, 4).map((tag) => (
                            <span
                              key={tag}
                              className="rounded bg-muted px-1.5 py-0.5 text-[9px] text-muted-foreground"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="border-t bg-muted/10 px-4 py-2.5">
                      <button
                        type="button"
                        onClick={() => void handleInstall(tool.slug)}
                        disabled={isInstalling || isInstalled}
                        className={cn(
                          'btn-press inline-flex w-full items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed',
                          isInstalled
                            ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900 dark:text-emerald-300'
                            : 'bg-primary text-primary-foreground hover:opacity-90 disabled:opacity-50',
                        )}
                      >
                        {isInstalling ? (
                          <>
                            <Loader2 className="h-3 w-3 animate-spin" />
                            Installing…
                          </>
                        ) : isInstalled ? (
                          <>
                            <Check className="h-3 w-3" />
                            Installed
                          </>
                        ) : (
                          <>
                            <Download className="h-3 w-3" />
                            Install
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
