import { useState, useCallback } from 'react'
import { useDocumentTitle } from '@/hooks'
import { Store, ExternalLink, Download, Tag, Lock } from 'lucide-react'
import { api, ApiError } from '@/api/client'
import { useToastStore } from '@/stores/toastStore'
import { PageHeader } from '@/components/ui/PageHeader'
import { Spinner } from '@/components/ui/Spinner'
import { cn } from '@/lib/utils'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

interface ImportResponse {
  imported: number
  errors: number
  resources: string[]
  error_details: string[]
}

interface FeaturedRepo {
  name: string
  description: string
  url: string
  tags: string[]
}

/* ------------------------------------------------------------------ */
/* Data                                                                */
/* ------------------------------------------------------------------ */

const FEATURED_REPOS: FeaturedRepo[] = [
  {
    name: 'Research Crew Starter',
    description: 'Two-agent research + writing crew with LLM connection',
    url: 'built-in',
    tags: ['starter', 'research'],
  },
  {
    name: 'Content Pipeline',
    description: 'Multi-step content creation pipeline with SEO optimization',
    url: 'coming-soon',
    tags: ['content', 'pipeline'],
  },
  {
    name: 'Customer Support Triage',
    description: 'AI-powered support ticket classification and routing with sentiment analysis',
    url: 'coming-soon',
    tags: ['support', 'classification', 'sentiment'],
  },
  {
    name: 'Code Review Pipeline',
    description: 'Automated code review with security scanning, style checking, and PR summary',
    url: 'coming-soon',
    tags: ['devtools', 'code-review', 'security'],
  },
  {
    name: 'Data Analysis Crew',
    description: 'Multi-agent data analysis: cleaner, analyst, and visualizer working together',
    url: 'coming-soon',
    tags: ['data', 'analysis', 'visualization'],
  },
  {
    name: 'SEO Content Writer',
    description: 'Research keywords, write SEO-optimized articles, and generate meta descriptions',
    url: 'coming-soon',
    tags: ['content', 'seo', 'marketing'],
  },
]

/* ------------------------------------------------------------------ */
/* Tag badge                                                           */
/* ------------------------------------------------------------------ */

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

/* ------------------------------------------------------------------ */
/* Featured repo card                                                  */
/* ------------------------------------------------------------------ */

function RepoCard({
  repo,
  onImport,
  importing,
}: {
  repo: FeaturedRepo
  onImport: (url: string) => void
  importing: boolean
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
      {/* Header */}
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

      {/* Body */}
      <div className="flex flex-1 flex-col gap-3 px-4 py-3">
        <p className="text-sm leading-relaxed text-muted-foreground">{repo.description}</p>
        <div className="flex flex-wrap gap-1.5">
          {repo.tags.map((tag) => (
            <TagBadge key={tag} tag={tag} />
          ))}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t bg-muted/10 px-4 py-3">
        <button
          onClick={() => onImport(repo.url)}
          disabled={isComingSoon || importing}
          aria-busy={importing || undefined}
          aria-label={isComingSoon ? `${repo.name} is coming soon` : `Import ${repo.name}`}
          className={cn(
            'inline-flex w-full items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
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

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export default function Marketplace() {
  const [url, setUrl] = useState('')
  const [importing, setImporting] = useState(false)
  const [importingBuiltIn, setImportingBuiltIn] = useState(false)
  const success = useToastStore((s) => s.success)
  const error = useToastStore((s) => s.error)
  const info = useToastStore((s) => s.info)

  useDocumentTitle('Marketplace')

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

        // Clear URL input on success
        if (!isBuiltIn && result.imported > 0) {
          setUrl('')
        }
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : 'Import failed. Check the URL and try again.'
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
        {/* Header */}
        <div className="mb-8">
          <PageHeader
            title="Marketplace"
            description="Browse and import agents, crews, and tools from git repositories"
          />
        </div>

        {/* Import from URL section */}
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

        {/* Featured repos section */}
        <section aria-labelledby="featured-heading">
          <h2
            id="featured-heading"
            className="mb-3 text-lg font-semibold tracking-tight text-foreground"
          >
            Featured
          </h2>
          <p className="mb-5 text-sm text-muted-foreground">
            Curated starter kits and community-contributed resource packs.
          </p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURED_REPOS.map((repo) => (
              <RepoCard
                key={repo.name}
                repo={repo}
                onImport={(repoUrl) => void handleImport(repoUrl)}
                importing={repo.url === 'built-in' ? importingBuiltIn : false}
              />
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
