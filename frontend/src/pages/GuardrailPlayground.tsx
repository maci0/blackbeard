import { useState, useEffect, useCallback, useMemo } from 'react'
import { ShieldCheck, Play, CheckCircle2, XCircle, AlertTriangle } from 'lucide-react'
import { api } from '@/api/client'
import { PageHeader } from '@/components/ui/PageHeader'
import { Spinner } from '@/components/ui/Spinner'
import { cn, getErrorMessage } from '@/lib/utils'
import { useDocumentTitle } from '@/hooks'
import type { Resource } from '@/lib/types'

interface RuleResult {
  rule: string
  passed: boolean
  detail: string
}

interface TestResult {
  passed: boolean
  guardrailName: string
  guardrailType: string
  results: RuleResult[]
}

function evaluateGuardrail(guardrail: Resource, input: string): TestResult {
  const spec = guardrail.spec
  const guardrailType = (spec.type as string | undefined) ?? 'unknown'
  const results: RuleResult[] = []

  if (guardrailType === 'pii') {
    const entities = (spec.pii_entities as string[] | undefined) ?? []
    const piiAction = (spec.pii_action as string | undefined) ?? 'redact'

    const PII_PATTERNS: Record<string, RegExp> = {
      EMAIL_ADDRESS: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
      PHONE_NUMBER: /(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}/g,
      CREDIT_CARD: /\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b/g,
      US_SSN: /\b\d{3}-\d{2}-\d{4}\b/g,
      IP_ADDRESS: /\b(?:\d{1,3}\.){3}\d{1,3}\b/g,
    }

    for (const entity of entities) {
      const pattern = PII_PATTERNS[entity]
      if (pattern) {
        const matches = input.match(pattern)
        if (matches) {
          results.push({
            rule: `PII: ${entity}`,
            passed: false,
            detail: `Found ${matches.length} match${matches.length !== 1 ? 'es' : ''} (action: ${piiAction})`,
          })
        } else {
          results.push({
            rule: `PII: ${entity}`,
            passed: true,
            detail: 'No matches found',
          })
        }
      } else {
        results.push({
          rule: `PII: ${entity}`,
          passed: true,
          detail: 'Pattern not available for client-side check',
        })
      }
    }
  } else if (guardrailType === 'llm') {
    const llmPrompt = (spec.llm_prompt as string | undefined) ?? ''
    results.push({
      rule: 'LLM Prompt Guard',
      passed: true,
      detail: llmPrompt
        ? `Prompt configured (${llmPrompt.length} chars) - requires server-side evaluation`
        : 'No prompt configured',
    })
  } else if (guardrailType === 'function') {
    const functionPath = (spec.function_path as string | undefined) ?? ''
    results.push({
      rule: 'Function Guard',
      passed: true,
      detail: functionPath
        ? `Function: ${functionPath} - requires server-side evaluation`
        : 'No function path configured',
    })
  } else if (guardrailType === 'schema') {
    const jsonSchema = spec.json_schema as Record<string, unknown> | undefined
    if (jsonSchema) {
      try {
        JSON.parse(input)
        results.push({
          rule: 'JSON Schema Validation',
          passed: true,
          detail: 'Input is valid JSON (full schema validation requires server-side evaluation)',
        })
      } catch {
        results.push({
          rule: 'JSON Schema Validation',
          passed: false,
          detail: 'Input is not valid JSON',
        })
      }
    } else {
      results.push({
        rule: 'JSON Schema Validation',
        passed: true,
        detail: 'No schema configured',
      })
    }
  }

  if (results.length === 0) {
    results.push({
      rule: 'General',
      passed: true,
      detail: 'No client-side rules to evaluate',
    })
  }

  const allPassed = results.every((r) => r.passed)

  return {
    passed: allPassed,
    guardrailName: guardrail.metadata.name,
    guardrailType,
    results,
  }
}

function GuardrailSpecDisplay({ spec }: { spec: Record<string, unknown> }) {
  const guardrailType = (spec.type as string | undefined) ?? 'unknown'
  const description = spec.description as string | undefined
  const onFail = (spec.on_fail as string | undefined) ?? 'reject'
  const llmPrompt = (spec.llm_prompt as string | undefined) ?? ''
  const functionPath = (spec.function_path as string | undefined) ?? ''

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-semibold',
            guardrailType === 'pii' &&
              'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300',
            guardrailType === 'llm' &&
              'border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300',
            guardrailType === 'function' &&
              'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-300',
            guardrailType === 'schema' &&
              'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300',
          )}
        >
          {guardrailType}
        </span>
        <span className="inline-flex items-center rounded-md border border-border px-2 py-0.5 text-xs font-medium text-muted-foreground">
          on_fail: {onFail}
        </span>
      </div>

      {description && <p className="text-sm text-muted-foreground">{description}</p>}

      {guardrailType === 'pii' && (
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Entities</p>
          <div className="flex flex-wrap gap-1">
            {((spec.pii_entities as string[] | undefined) ?? []).map((entity) => (
              <span
                key={entity}
                className="inline-flex items-center rounded border border-rose-100 bg-rose-50 px-1.5 py-0.5 text-xs text-rose-700 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-300"
              >
                {entity}
              </span>
            ))}
          </div>
        </div>
      )}

      {guardrailType === 'llm' && llmPrompt && (
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Prompt</p>
          <pre className="max-h-32 overflow-auto rounded-md border bg-muted/60 p-2 text-xs">
            {llmPrompt}
          </pre>
        </div>
      )}

      {guardrailType === 'function' && functionPath && (
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Function</p>
          <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">{functionPath}</code>
        </div>
      )}
    </div>
  )
}

function ResultPanel({ result }: { result: TestResult }) {
  return (
    <div className="space-y-4">
      <div
        className={cn(
          'flex items-center gap-3 rounded-lg border p-4',
          result.passed
            ? 'border-emerald-200 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950'
            : 'border-red-200 bg-red-50 dark:border-red-800 dark:bg-red-950',
        )}
      >
        {result.passed ? (
          <CheckCircle2 className="h-6 w-6 shrink-0 text-emerald-600 dark:text-emerald-400" />
        ) : (
          <XCircle className="h-6 w-6 shrink-0 text-red-600 dark:text-red-400" />
        )}
        <div>
          <p
            className={cn(
              'text-sm font-semibold',
              result.passed
                ? 'text-emerald-800 dark:text-emerald-200'
                : 'text-red-800 dark:text-red-200',
            )}
          >
            {result.passed ? 'PASS' : 'FAIL'}
          </p>
          <p className="text-xs text-muted-foreground">
            {result.guardrailName} ({result.guardrailType})
          </p>
        </div>
      </div>

      <div className="space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Rule Results
        </p>
        {result.results.map((r, idx) => (
          <div
            key={idx}
            className={cn(
              'flex items-start gap-2 rounded-md border p-3',
              r.passed
                ? 'border-emerald-100 bg-card dark:border-emerald-900'
                : 'border-red-100 bg-card dark:border-red-900',
            )}
          >
            {r.passed ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
            ) : (
              <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
            )}
            <div className="min-w-0">
              <p className="text-sm font-medium text-foreground">{r.rule}</p>
              <p className="text-xs text-muted-foreground">{r.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function GuardrailPlayground() {
  useDocumentTitle('Guardrail Playground')

  const [guardrails, setGuardrails] = useState<Resource[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [selectedName, setSelectedName] = useState('')
  const [testInput, setTestInput] = useState('')
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testing, setTesting] = useState(false)

  const fetchGuardrails = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.get<{ items: Resource[]; total: number }>('/api/v1/guardrails')
      setGuardrails(result.items)
      if (result.items.length > 0 && !selectedName) {
        setSelectedName(result.items[0]!.metadata.name)
      }
    } catch (err) {
      setError(getErrorMessage(err, 'Failed to load guardrails'))
    } finally {
      setLoading(false)
    }
  }, [selectedName])

  useEffect(() => {
    void fetchGuardrails()
  }, [fetchGuardrails])

  const selectedGuardrail = useMemo(
    () => guardrails.find((g) => g.metadata.name === selectedName) ?? null,
    [guardrails, selectedName],
  )

  const handleRunTest = useCallback(() => {
    if (!selectedGuardrail || !testInput.trim()) return
    setTesting(true)
    setTestResult(null)

    requestAnimationFrame(() => {
      const result = evaluateGuardrail(selectedGuardrail, testInput)
      setTestResult(result)
      setTesting(false)
    })
  }, [selectedGuardrail, testInput])

  if (loading) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div role="status" className="flex items-center gap-2 text-muted-foreground">
          <Spinner size="md" className="text-muted-foreground" />
          <span className="text-sm">Loading guardrails...</span>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="mx-auto mb-3 h-8 w-8 text-destructive" aria-hidden="true" />
          <p className="font-medium">{error}</p>
          <button
            onClick={() => void fetchGuardrails()}
            className="mt-4 rounded-md border px-4 py-2 text-sm transition-colors hover:bg-accent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (guardrails.length === 0) {
    return (
      <div className="page-enter flex-1 overflow-auto p-6">
        <PageHeader
          title="Guardrail Playground"
          description="Test guardrail rules against sample inputs"
        />
        <div className="mt-12 flex flex-col items-center justify-center text-center">
          <ShieldCheck className="mb-4 h-12 w-12 text-muted-foreground/60" aria-hidden="true" />
          <h2 className="text-base font-medium text-foreground">No guardrails found</h2>
          <p className="mt-1 max-w-xs text-sm text-muted-foreground">
            Create a guardrail resource first to test it here.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="page-enter flex-1 overflow-auto p-6">
      <PageHeader
        title="Guardrail Playground"
        description="Test guardrail rules against sample inputs before deploying"
      />

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <div className="space-y-4">
          <div>
            <label
              htmlFor="guardrail-select"
              className="mb-1.5 block text-sm font-semibold text-foreground"
            >
              Guardrail
            </label>
            <select
              id="guardrail-select"
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              value={selectedName}
              onChange={(e) => {
                setSelectedName(e.target.value)
                setTestResult(null)
              }}
            >
              {guardrails.map((g) => (
                <option key={g.metadata.name} value={g.metadata.name}>
                  {g.metadata.name}
                </option>
              ))}
            </select>
          </div>

          {selectedGuardrail && (
            <div className="rounded-lg border bg-card p-4">
              <p className="mb-3 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                Configuration
              </p>
              <GuardrailSpecDisplay spec={selectedGuardrail.spec} />
            </div>
          )}
        </div>

        <div className="space-y-4">
          <div>
            <label
              htmlFor="test-input"
              className="mb-1.5 block text-sm font-semibold text-foreground"
            >
              Test Input
            </label>
            <textarea
              id="test-input"
              className="h-48 w-full resize-none rounded-md border border-border bg-background p-3 text-sm text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Enter text to test against the guardrail rules..."
              value={testInput}
              onChange={(e) => setTestInput(e.target.value)}
            />
          </div>

          <button
            onClick={handleRunTest}
            disabled={!selectedGuardrail || !testInput.trim() || testing}
            aria-busy={testing}
            className="inline-flex w-full items-center justify-center gap-2 rounded-md bg-primary px-4 py-2.5 text-sm font-medium text-primary-foreground shadow-sm transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
          >
            {testing ? (
              <Spinner size="sm" className="text-current" />
            ) : (
              <Play className="h-4 w-4" />
            )}
            Run Test
          </button>

          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() =>
                setTestInput('Contact me at john.doe@example.com or call 555-123-4567')
              }
              className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              PII sample
            </button>
            <button
              type="button"
              onClick={() => setTestInput('My SSN is 123-45-6789 and card is 4111 1111 1111 1111')}
              className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Sensitive data
            </button>
            <button
              type="button"
              onClick={() => setTestInput('This is a clean message with no sensitive information.')}
              className="rounded-md border px-2 py-1 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              Clean text
            </button>
          </div>
        </div>

        <div>
          <p className="mb-1.5 text-sm font-semibold text-foreground">Results</p>
          {testResult ? (
            <ResultPanel result={testResult} />
          ) : (
            <div className="flex h-48 items-center justify-center rounded-lg border border-dashed bg-muted/20">
              <p className="text-sm text-muted-foreground">
                Select a guardrail and run a test to see results
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
