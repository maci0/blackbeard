import { useState, useCallback, useMemo, useRef, useEffect } from 'react'
import { useShallow } from 'zustand/react/shallow'
import { HelpCircle, X, AlertCircle } from 'lucide-react'
import { useStudioStore } from '@/stores/studioStore'
import { cn } from '@/lib/utils'

interface ExpressionEditorProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  fieldId?: string
}

function validateExpression(expr: string): string | null {
  if (!expr.trim()) return null

  let parens = 0
  let brackets = 0
  for (const ch of expr) {
    if (ch === '(') parens++
    if (ch === ')') parens--
    if (ch === '[') brackets++
    if (ch === ']') brackets--
    if (parens < 0) return 'Unexpected closing parenthesis'
    if (brackets < 0) return 'Unexpected closing bracket'
  }
  if (parens > 0) return `${parens} unclosed parenthes${parens === 1 ? 'is' : 'es'}`
  if (brackets > 0) return `${brackets} unclosed bracket${brackets === 1 ? '' : 's'}`

  const operators = ['==', '!=', '>=', '<=', '>', '<', 'and', 'or', 'not', 'in']
  const hasOperator =
    operators.some((op) => expr.includes(op)) ||
    /^[a-zA-Z_][\w.]*$/.test(expr.trim()) ||
    /^['"]/.test(expr.trim()) ||
    /^\d/.test(expr.trim())

  if (!hasOperator && expr.trim().length > 0) {
    return 'Expression may be missing an operator (==, !=, >, <, and, or)'
  }

  return null
}

export function ExpressionEditor({ value, onChange, placeholder, fieldId }: ExpressionEditorProps) {
  const [helpOpen, setHelpOpen] = useState(false)
  const helpRef = useRef<HTMLDivElement>(null)
  const btnRef = useRef<HTMLButtonElement>(null)

  const stepNames = useStudioStore(
    useShallow((state) =>
      state.nodes
        .filter(
          (n) =>
            n.type === 'flowStep' ||
            n.type === 'condition' ||
            n.type === 'router' ||
            n.type === 'parallel',
        )
        .map((n) => (n.data['name'] as string | undefined) ?? '')
        .filter(Boolean),
    ),
  )

  const validationError = useMemo(() => validateExpression(value), [value])

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      onChange(e.target.value)
    },
    [onChange],
  )

  useEffect(() => {
    if (!helpOpen) return
    const handler = (e: MouseEvent) => {
      if (
        helpRef.current &&
        !helpRef.current.contains(e.target as Node) &&
        btnRef.current &&
        !btnRef.current.contains(e.target as Node)
      ) {
        setHelpOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [helpOpen])

  return (
    <div className="relative">
      <div className="relative">
        <textarea
          id={fieldId || undefined}
          className={cn(
            'w-full resize-none rounded-md border bg-background px-2.5 py-1.5 font-mono text-xs text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
            validationError ? 'border-red-400 dark:border-red-600' : 'border-border',
          )}
          rows={3}
          value={value}
          onChange={handleChange}
          placeholder={placeholder}
          autoComplete="off"
          spellCheck={false}
        />
        <button
          ref={btnRef}
          type="button"
          onClick={() => setHelpOpen((v) => !v)}
          aria-label="Expression syntax help"
          aria-expanded={helpOpen}
          className="absolute right-1.5 top-1.5 flex h-5 w-5 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          <HelpCircle className="h-3.5 w-3.5" />
        </button>
      </div>

      {validationError && (
        <div className="mt-1 flex items-center gap-1 text-[10px] text-red-500 dark:text-red-400">
          <AlertCircle className="h-3 w-3 shrink-0" aria-hidden="true" />
          <span>{validationError}</span>
        </div>
      )}

      {helpOpen && (
        <div
          ref={helpRef}
          role="dialog"
          aria-label="Expression syntax reference"
          className="absolute right-0 top-full z-30 mt-1 w-72 rounded-lg border bg-card p-3 shadow-lg"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs font-semibold text-foreground">Syntax Reference</span>
            <button
              type="button"
              onClick={() => setHelpOpen(false)}
              className="flex h-5 w-5 items-center justify-center rounded text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              aria-label="Close help"
            >
              <X className="h-3 w-3" />
            </button>
          </div>

          <div className="space-y-2.5 text-[11px]">
            <div>
              <p className="font-semibold text-muted-foreground">State Variables</p>
              <code className="mt-0.5 block rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                state.result
              </code>
              <code className="mt-0.5 block rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                state.status
              </code>
            </div>

            {stepNames.length > 0 && (
              <div>
                <p className="font-semibold text-muted-foreground">Step Outputs</p>
                {stepNames.slice(0, 5).map((name) => (
                  <code
                    key={name}
                    className="mt-0.5 block rounded bg-muted px-1.5 py-0.5 font-mono text-foreground"
                  >
                    steps.{name}.output
                  </code>
                ))}
                {stepNames.length > 5 && (
                  <p className="mt-0.5 text-muted-foreground">...and {stepNames.length - 5} more</p>
                )}
              </div>
            )}

            <div>
              <p className="font-semibold text-muted-foreground">Operators</p>
              <div className="mt-0.5 flex flex-wrap gap-1">
                {['==', '!=', '>', '<', '>=', '<=', 'and', 'or', 'not', 'in'].map((op) => (
                  <code
                    key={op}
                    className="rounded bg-muted px-1.5 py-0.5 font-mono text-foreground"
                  >
                    {op}
                  </code>
                ))}
              </div>
            </div>

            <div>
              <p className="font-semibold text-muted-foreground">Examples</p>
              <code className="mt-0.5 block rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                state.status == &apos;approved&apos;
              </code>
              <code className="mt-0.5 block rounded bg-muted px-1.5 py-0.5 font-mono text-foreground">
                state.score &gt; 0.8 and state.ready
              </code>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
