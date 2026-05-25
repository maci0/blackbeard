import { useState, useCallback, useMemo } from 'react'
import { useDocumentTitle } from '@/hooks'
import { Store, ExternalLink, Download, Tag, Lock, Search, Eye, Package } from 'lucide-react'
import * as Dialog from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import { api } from '@/api/client'
import { useToastStore } from '@/stores/toastStore'
import { PageHeader } from '@/components/ui/PageHeader'
import { Spinner } from '@/components/ui/Spinner'
import { cn, getErrorMessage } from '@/lib/utils'

interface ImportResponse {
  imported: number
  errors: number
  resources: string[]
  error_details: string[]
}

interface ResourceCount {
  agents: number
  tasks: number
  crews: number
  tools: number
  llmConnections: number
}

interface FeaturedRepo {
  name: string
  description: string
  url: string
  tags: string[]
  category: string
  resources: ResourceCount
  useCase: string
}

const FEATURED_REPOS: FeaturedRepo[] = [
  {
    name: 'Research Crew Starter',
    description: 'Two-agent research + writing crew with LLM connection',
    url: 'built-in',
    tags: ['starter', 'research'],
    category: 'Starter',
    resources: { agents: 2, tasks: 2, crews: 1, tools: 1, llmConnections: 1 },
    useCase:
      'Get started quickly with a researcher and writer agent that collaborate to produce reports on any topic.',
  },
  {
    name: 'Content Pipeline',
    description: 'Multi-step content creation pipeline with SEO optimization',
    url: 'built-in',
    tags: ['content', 'pipeline'],
    category: 'Content',
    resources: { agents: 3, tasks: 3, crews: 1, tools: 0, llmConnections: 1 },
    useCase:
      'Automate content creation with agents for research, writing, and SEO optimization working in sequence.',
  },
  {
    name: 'Customer Support Triage',
    description: 'AI-powered support ticket classification and routing with sentiment analysis',
    url: 'built-in',
    tags: ['support', 'classification', 'sentiment'],
    category: 'Support',
    resources: { agents: 3, tasks: 3, crews: 1, tools: 0, llmConnections: 1 },
    useCase:
      'Classify incoming support tickets, analyze sentiment, and route to the right team automatically.',
  },
  {
    name: 'Code Review Pipeline',
    description: 'Automated code review with security scanning, style checking, and PR summary',
    url: 'built-in',
    tags: ['devtools', 'code-review', 'security'],
    category: 'DevTools',
    resources: { agents: 3, tasks: 3, crews: 1, tools: 0, llmConnections: 0 },
    useCase:
      'Review code changes with security scanning, style analysis, and automated PR summaries.',
  },
  {
    name: 'Data Analysis Crew',
    description: 'Multi-agent data analysis: cleaner, analyst, and visualizer working together',
    url: 'built-in',
    tags: ['data', 'analysis', 'visualization'],
    category: 'Data',
    resources: { agents: 3, tasks: 3, crews: 1, tools: 0, llmConnections: 1 },
    useCase:
      'Clean, analyze, and visualize data with specialized agents for each stage of the pipeline.',
  },
  {
    name: 'SEO Content Writer',
    description: 'Research keywords, write SEO-optimized articles, and generate meta descriptions',
    url: 'built-in',
    tags: ['content', 'seo', 'marketing'],
    category: 'SEO',
    resources: { agents: 3, tasks: 3, crews: 1, tools: 0, llmConnections: 1 },
    useCase:
      'Research target keywords, write optimized articles, and generate meta tags for search rankings.',
  },
]

const CATEGORIES = ['All', 'Starter', 'Content', 'Support', 'DevTools', 'Data', 'SEO'] as const

const TAG_CLASSES: Record<string, string> = {
  starter:
    'bg-emerald-100 text-emerald-700 border-emerald-200 dark:bg-emerald-900/40 dark:text-emerald-300 dark:border-emerald-800',
  research:
    'bg-blue-100 text-blue-700 border-blue-200 dark:bg-blue-900/40 dark:text-blue-300 dark:border-blue-800',
  content:
    'bg-amber-100 text-amber-700 border-amber-200 dark:bg-amber-900/40 dark:text-amber-300 dark:border-amber-800',
  pipeline:
    'bg-violet-100 text-violet-700 border-violet-200 dark:bg-violet-900/40 dark:text-violet-300 dark:border-violet-800',
  support:
    'bg-rose-100 text-rose-700 border-rose-200 dark:bg-rose-900/40 dark:text-rose-300 dark:border-rose-800',
  classification:
    'bg-sky-100 text-sky-700 border-sky-200 dark:bg-sky-900/40 dark:text-sky-300 dark:border-sky-800',
  sentiment:
    'bg-pink-100 text-pink-700 border-pink-200 dark:bg-pink-900/40 dark:text-pink-300 dark:border-pink-800',
  devtools:
    'bg-slate-100 text-slate-700 border-slate-200 dark:bg-slate-900/40 dark:text-slate-300 dark:border-slate-800',
  'code-review':
    'bg-cyan-100 text-cyan-700 border-cyan-200 dark:bg-cyan-900/40 dark:text-cyan-300 dark:border-cyan-800',
  security:
    'bg-red-100 text-red-700 border-red-200 dark:bg-red-900/40 dark:text-red-300 dark:border-red-800',
  data: 'bg-indigo-100 text-indigo-700 border-indigo-200 dark:bg-indigo-900/40 dark:text-indigo-300 dark:border-indigo-800',
  analysis:
    'bg-teal-100 text-teal-700 border-teal-200 dark:bg-teal-900/40 dark:text-teal-300 dark:border-teal-800',
  visualization:
    'bg-fuchsia-100 text-fuchsia-700 border-fuchsia-200 dark:bg-fuchsia-900/40 dark:text-fuchsia-300 dark:border-fuchsia-800',
  seo: 'bg-orange-100 text-orange-700 border-orange-200 dark:bg-orange-900/40 dark:text-orange-300 dark:border-orange-800',
  marketing:
    'bg-lime-100 text-lime-700 border-lime-200 dark:bg-lime-900/40 dark:text-lime-300 dark:border-lime-800',
}

function TagBadge({ tag }: { tag: string }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-0.5 rounded-full border px-1.5 py-px text-[10px] font-medium',
        TAG_CLASSES[tag] ??
          'border-gray-200 bg-gray-100 text-gray-600 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300',
      )}
    >
      <Tag className="h-2.5 w-2.5" aria-hidden="true" />
      {tag}
    </span>
  )
}

function ResourceSummary({ resources }: { resources: ResourceCount }) {
  const parts: string[] = []
  if (resources.agents > 0)
    parts.push(`${resources.agents} agent${resources.agents !== 1 ? 's' : ''}`)
  if (resources.tasks > 0) parts.push(`${resources.tasks} task${resources.tasks !== 1 ? 's' : ''}`)
  if (resources.crews > 0) parts.push(`${resources.crews} crew${resources.crews !== 1 ? 's' : ''}`)
  if (resources.tools > 0) parts.push(`${resources.tools} tool${resources.tools !== 1 ? 's' : ''}`)
  if (resources.llmConnections > 0)
    parts.push(
      `${resources.llmConnections} LLM connection${resources.llmConnections !== 1 ? 's' : ''}`,
    )
  const total =
    resources.agents +
    resources.tasks +
    resources.crews +
    resources.tools +
    resources.llmConnections

  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <Package className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span>
        {total} resource{total !== 1 ? 's' : ''}: {parts.join(', ')}
      </span>
    </div>
  )
}

function PreviewDialog({
  repo,
  open,
  onOpenChange,
}: {
  repo: FeaturedRepo | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  if (!repo) return null

  const { resources } = repo
  const lines: { kind: string; count: number }[] = []
  if (resources.agents > 0) lines.push({ kind: 'Agent', count: resources.agents })
  if (resources.tasks > 0) lines.push({ kind: 'Task', count: resources.tasks })
  if (resources.crews > 0) lines.push({ kind: 'Crew', count: resources.crews })
  if (resources.tools > 0) lines.push({ kind: 'Tool', count: resources.tools })
  if (resources.llmConnections > 0)
    lines.push({ kind: 'LLM Connection', count: resources.llmConnections })

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out data-[state=open]:fade-in" />
        <Dialog.Content
          aria-describedby="preview-dialog-desc"
          className="fixed left-1/2 top-1/2 z-50 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border bg-card p-6 shadow-lg data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
        >
          <Dialog.Title className="text-lg font-semibold">{repo.name}</Dialog.Title>
          <Dialog.Description
            id="preview-dialog-desc"
            className="mt-1 text-sm text-muted-foreground"
          >
            {repo.description}
          </Dialog.Description>

          <div className="mt-4 space-y-4">
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Use Case
              </h3>
              <p className="mt-1 text-sm leading-relaxed text-foreground">{repo.useCase}</p>
            </div>

            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Resources Included
              </h3>
              <ul className="mt-2 space-y-1.5" role="list">
                {lines.map((line) => (
                  <li
                    key={line.kind}
                    className="flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-sm"
                  >
                    <span className="font-medium text-foreground">{line.kind}</span>
                    <span className="text-muted-foreground">
                      {line.count} resource{line.count !== 1 ? 's' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </div>

            <div className="flex flex-wrap gap-1.5">
              {repo.tags.map((tag) => (
                <TagBadge key={tag} tag={tag} />
              ))}
            </div>
          </div>

          <div className="mt-6 flex justify-end">
            <Dialog.Close asChild>
              <button
                type="button"
                className="rounded-md border px-4 py-2 text-sm transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Close
              </button>
            </Dialog.Close>
          </div>

          <Dialog.Close asChild>
            <button
              type="button"
              className="absolute right-3 top-3 flex h-[44px] w-[44px] items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close"
              title="Close"
            >
              <X className="h-4 w-4" />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}

function RepoCard({
  repo,
  onImport,
  importing,
  onPreview,
}: {
  repo: FeaturedRepo
  onImport: (url: string) => void
  importing: boolean
  onPreview: (repo: FeaturedRepo) => void
}) {
  const isComingSoon = repo.url === 'coming-soon'
  const isBuiltIn = repo.url === 'built-in'

  return (
    <div
      className={cn(
        'flex flex-col overflow-hidden rounded-lg border bg-card shadow-sm transition-all duration-200',
        !isComingSoon && 'hover:-translate-y-0.5 hover:shadow-lg',
      )}
    >
      <div className="border-b bg-muted/20 px-4 pb-3 pt-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex min-w-0 items-center gap-2.5">
            <div className="shrink-0 rounded-md border border-indigo-200 bg-indigo-100 p-1.5 dark:border-indigo-800 dark:bg-indigo-900/50">
              <Store className="h-4 w-4 text-indigo-600 dark:text-indigo-400" aria-hidden="true" />
            </div>
            <p className="truncate text-sm font-semibold" title={repo.name}>
              {repo.name}
            </p>
          </div>
          {isBuiltIn && (
            <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary">
              Built-in
            </span>
          )}
          {isComingSoon && (
            <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
              Coming soon
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-3 px-4 py-3">
        <p className="text-sm leading-relaxed text-muted-foreground">{repo.description}</p>
        <ResourceSummary resources={repo.resources} />
        <div className="flex flex-wrap gap-1.5">
          {repo.tags.map((tag) => (
            <TagBadge key={tag} tag={tag} />
          ))}
        </div>
      </div>

      <div className="flex gap-2 border-t bg-muted/10 px-4 py-3">
        <button
          onClick={() => onPreview(repo)}
          aria-label={`Preview ${repo.name}`}
          className="inline-flex items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-medium transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <Eye className="h-3.5 w-3.5" aria-hidden="true" />
          Preview
        </button>
        <button
          onClick={() => onImport(repo.url)}
          disabled={isComingSoon || importing}
          aria-busy={importing || undefined}
          aria-label={isComingSoon ? `${repo.name} is coming soon` : `Import ${repo.name}`}
          className={cn(
            'inline-flex flex-1 items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            isComingSoon
              ? 'cursor-not-allowed border bg-muted text-muted-foreground'
              : 'bg-primary text-primary-foreground hover:opacity-90',
          )}
        >
          {isComingSoon ? (
            <>
              <Lock className="h-3.5 w-3.5" aria-hidden="true" />
              Coming Soon
            </>
          ) : importing ? (
            <>
              <Spinner size="sm" label="Importing" />
              Importing...
            </>
          ) : (
            <>
              <Download className="h-3.5 w-3.5" aria-hidden="true" />
              Import
            </>
          )}
        </button>
      </div>
    </div>
  )
}

export default function Marketplace() {
  const [url, setUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importingBuiltIn, setImportingBuiltIn] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [activeCategory, setActiveCategory] = useState<string>('All')
  const [previewRepo, setPreviewRepo] = useState<FeaturedRepo | null>(null)
  const success = useToastStore((s) => s.success)
  const error = useToastStore((s) => s.error)
  const info = useToastStore((s) => s.info)

  useDocumentTitle('Marketplace')

  const filteredRepos = useMemo(() => {
    let repos = FEATURED_REPOS

    if (activeCategory !== 'All') {
      repos = repos.filter((r) => r.category === activeCategory)
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      repos = repos.filter(
        (r) =>
          r.name.toLowerCase().includes(q) ||
          r.description.toLowerCase().includes(q) ||
          r.tags.some((t) => t.toLowerCase().includes(q)),
      )
    }

    return repos
  }, [searchQuery, activeCategory])

  const handleImport = useCallback(
    async (importUrl: string) => {
      const isBuiltIn = importUrl === 'built-in'
      if (isBuiltIn) {
        setImportingBuiltIn(true)
      } else {
        setImporting(true)
      }

      try {
        const result = await api.post<ImportResponse>('/api/v1/marketplace/import', {
          url: importUrl,
        })

        if (result.imported > 0) {
          success(
            `Imported ${result.imported} resource${result.imported === 1 ? '' : 's'}: ${result.resources.join(', ')}`,
          )
        }
        if (result.errors > 0) {
          error(
            `${result.errors} error${result.errors === 1 ? '' : 's'} during import${result.error_details.length > 0 ? `: ${result.error_details[0]}` : ''}`,
          )
        }
        if (result.imported === 0 && result.errors === 0) {
          info('No resources found to import')
        }

        if (!isBuiltIn && result.imported > 0) {
          setUrl('')
        }
      } catch (err) {
        const message = getErrorMessage(err, 'Import failed. Check the URL and try again.')
        error(message)
      } finally {
        if (isBuiltIn) {
          setImportingBuiltIn(false)
        } else {
          setImporting(false)
        }
      }
    },
    [success, error, info],
  )

  const handleUrlImport = useCallback(() => {
    const trimmed = url.trim()
    if (!trimmed) return
    try {
      const parsed = new URL(trimmed)
      if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
        error('Please enter an HTTPS URL (e.g. https://github.com/org/repo.git)')
        return
      }
    } catch {
      error('Please enter a valid URL (e.g. https://github.com/org/repo.git)')
      return
    }
    void handleImport(trimmed)
  }, [url, handleImport, error])

  return (
    <div className="page-enter flex-1 overflow-auto">
      <div className="mx-auto max-w-7xl p-6">
        <div className="mb-8">
          <PageHeader
            title="Marketplace"
            description="Browse and import agents, crews, and tools from git repositories"
          />
        </div>

        <section aria-labelledby="import-url-heading" className="mb-10">
          <h2
            id="import-url-heading"
            className="mb-3 text-lg font-semibold tracking-tight text-foreground"
          >
            Import from URL
          </h2>
          <p className="mb-4 text-sm text-muted-foreground">
            Paste a git HTTPS URL containing Blackbeard resource YAML files to import agents, crews,
            tools, and other resources.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault()
              handleUrlImport()
            }}
            noValidate
            className="flex flex-col gap-3 sm:flex-row"
          >
            <div className="relative flex-1">
              <label htmlFor="marketplace-url" className="sr-only">
                Git repository HTTPS URL
              </label>
              <ExternalLink
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                id="marketplace-url"
                type="url"
                placeholder="https://github.com/org/repo.git"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                autoComplete="off"
                disabled={importing}
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
              />
            </div>
            <button
              type="submit"
              disabled={!url.trim() || importing}
              aria-busy={importing || undefined}
              className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-5 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
            >
              {importing ? (
                <>
                  <Spinner size="sm" label="Importing from URL" />
                  Importing...
                </>
              ) : (
                <>
                  <Download className="h-4 w-4" aria-hidden="true" />
                  Import
                </>
              )}
            </button>
          </form>
        </section>

        <section aria-labelledby="featured-heading">
          <h2
            id="featured-heading"
            className="mb-3 text-lg font-semibold tracking-tight text-foreground"
          >
            Template Gallery
          </h2>
          <p className="mb-5 text-sm text-muted-foreground">
            Curated starter kits and community-contributed resource packs.
          </p>

          <div className="mb-6 space-y-4">
            <div className="relative max-w-md">
              <label htmlFor="marketplace-search" className="sr-only">
                Search templates
              </label>
              <Search
                aria-hidden="true"
                className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
              />
              <input
                id="marketplace-search"
                type="search"
                placeholder="Search templates..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                autoComplete="off"
                className="w-full rounded-md border bg-background py-2 pl-9 pr-3 text-sm placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>

            <div className="flex flex-wrap gap-2" role="group" aria-label="Category filters">
              {CATEGORIES.map((category) => (
                <button
                  key={category}
                  onClick={() => setActiveCategory(category)}
                  aria-pressed={activeCategory === category}
                  className={cn(
                    'rounded-full border px-3 py-1 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    activeCategory === category
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-background text-muted-foreground hover:bg-muted hover:text-foreground',
                  )}
                >
                  {category}
                </button>
              ))}
            </div>
          </div>

          {filteredRepos.length === 0 ? (
            <div className="rounded-lg border border-dashed bg-muted/20 px-6 py-12 text-center">
              <p className="text-sm font-medium text-muted-foreground">
                No templates match your search.
              </p>
              <p className="mt-1 text-xs text-muted-foreground/70">
                Try adjusting your search or category filter.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {filteredRepos.map((repo) => (
                <RepoCard
                  key={repo.name}
                  repo={repo}
                  onImport={(repoUrl) => void handleImport(repoUrl)}
                  importing={repo.url === 'built-in' ? importingBuiltIn : false}
                  onPreview={setPreviewRepo}
                />
              ))}
            </div>
          )}
        </section>
      </div>

      <PreviewDialog
        repo={previewRepo}
        open={!!previewRepo}
        onOpenChange={(open) => {
          if (!open) setPreviewRepo(null)
        }}
      />
    </div>
  )
}
