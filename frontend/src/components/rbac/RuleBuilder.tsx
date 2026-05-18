import { useState } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { ALL_PLURALS } from '@/lib/kinds'

/* ------------------------------------------------------------------ */
/* Constants                                                           */
/* ------------------------------------------------------------------ */

const RESOURCES = [...ALL_PLURALS, 'users'] as const

const VERBS = ['get', 'list', 'create', 'update', 'delete', 'run', 'invoke', 'delegate'] as const

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface Rule {
  resources: string[]
  verbs: string[]
  resourceNames?: string[]
}

interface RuleBuilderProps {
  rules: Rule[]
  onChange: (rules: Rule[]) => void
}

/* ------------------------------------------------------------------ */
/* Single rule row                                                     */
/* ------------------------------------------------------------------ */

function RuleRow({
  rule,
  index,
  canRemove,
  onChange,
  onRemove,
}: {
  rule: Rule
  index: number
  canRemove: boolean
  onChange: (rule: Rule) => void
  onRemove: () => void
}) {
  const [showNames, setShowNames] = useState((rule.resourceNames ?? []).length > 0)
  const [nameInput, setNameInput] = useState('')

  const toggleResource = (resource: string) => {
    const next = rule.resources.includes(resource)
      ? rule.resources.filter((r) => r !== resource)
      : [...rule.resources, resource]
    onChange({ ...rule, resources: next })
  }

  const toggleVerb = (verb: string) => {
    const next = rule.verbs.includes(verb)
      ? rule.verbs.filter((v) => v !== verb)
      : [...rule.verbs, verb]
    onChange({ ...rule, verbs: next })
  }

  const selectAllResources = () => {
    const allSelected = RESOURCES.every((r) => rule.resources.includes(r))
    onChange({
      ...rule,
      resources: allSelected ? [] : [...RESOURCES],
    })
  }

  const selectAllVerbs = () => {
    const allSelected = VERBS.every((v) => rule.verbs.includes(v))
    onChange({
      ...rule,
      verbs: allSelected ? [] : [...VERBS],
    })
  }

  const addName = () => {
    const trimmed = nameInput.trim()
    if (!trimmed) return
    const names = rule.resourceNames ?? []
    if (!names.includes(trimmed)) {
      onChange({ ...rule, resourceNames: [...names, trimmed] })
    }
    setNameInput('')
  }

  const removeName = (name: string) => {
    onChange({
      ...rule,
      resourceNames: (rule.resourceNames ?? []).filter((n) => n !== name),
    })
  }

  return (
    <fieldset className="rounded-md border bg-muted/10 p-4">
      <legend className="px-1 text-xs font-medium text-muted-foreground">Rule {index + 1}</legend>

      {/* Resources */}
      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">Resources</span>
          <button
            type="button"
            onClick={selectAllResources}
            className="text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {RESOURCES.every((r) => rule.resources.includes(r)) ? 'Deselect all' : 'Select all'}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {RESOURCES.map((resource) => {
            const checked = rule.resources.includes(resource)
            return (
              <label
                key={resource}
                className={`inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring ${
                  checked
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-border bg-background text-muted-foreground hover:bg-muted'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleResource(resource)}
                  className="sr-only"
                  aria-label={`Resource: ${resource}`}
                />
                {resource}
              </label>
            )
          })}
        </div>
      </div>

      {/* Verbs */}
      <div className="mb-3">
        <div className="mb-1.5 flex items-center justify-between">
          <span className="text-xs font-medium text-muted-foreground">Verbs</span>
          <button
            type="button"
            onClick={selectAllVerbs}
            className="text-xs text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            {VERBS.every((v) => rule.verbs.includes(v)) ? 'Deselect all' : 'Select all'}
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {VERBS.map((verb) => {
            const checked = rule.verbs.includes(verb)
            return (
              <label
                key={verb}
                className={`inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring ${
                  checked
                    ? 'border-emerald-400/40 bg-emerald-100/60 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                    : 'border-border bg-background text-muted-foreground hover:bg-muted'
                }`}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggleVerb(verb)}
                  className="sr-only"
                  aria-label={`Verb: ${verb}`}
                />
                {verb}
              </label>
            )
          })}
        </div>
      </div>

      {/* Resource names filter */}
      <div>
        {!showNames ? (
          <button
            type="button"
            onClick={() => setShowNames(true)}
            className="text-xs text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            + Add resource name filter
          </button>
        ) : (
          <div>
            <span className="mb-1 block text-xs font-medium text-muted-foreground">
              Resource names (optional)
            </span>
            <div className="flex gap-2">
              <label htmlFor={`rule-name-${index}`} className="sr-only">
                Resource name filter
              </label>
              <input
                id={`rule-name-${index}`}
                type="text"
                value={nameInput}
                onChange={(e) => setNameInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addName()
                  }
                }}
                placeholder="e.g. my-agent"
                className="flex-1 rounded-md border bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
              <button
                type="button"
                onClick={addName}
                className="rounded-md border px-2 py-1 text-xs transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                Add
              </button>
            </div>
            {(rule.resourceNames ?? []).length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {(rule.resourceNames ?? []).map((name) => (
                  <span
                    key={name}
                    className="inline-flex items-center gap-1 rounded bg-gray-100 px-1.5 py-0.5 text-xs dark:bg-gray-800"
                  >
                    {name}
                    <button
                      type="button"
                      onClick={() => removeName(name)}
                      aria-label={`Remove filter: ${name}`}
                      className="text-muted-foreground hover:text-foreground"
                    >
                      <Trash2 className="h-2.5 w-2.5" />
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Remove */}
      {canRemove && (
        <div className="mt-3 flex justify-end">
          <button
            type="button"
            onClick={onRemove}
            aria-label={`Remove rule ${index + 1}`}
            className="inline-flex items-center gap-1 rounded text-xs text-destructive transition-colors hover:text-destructive/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <Trash2 className="h-3 w-3" />
            Remove rule
          </button>
        </div>
      )}
    </fieldset>
  )
}

/* ------------------------------------------------------------------ */
/* RuleBuilder                                                         */
/* ------------------------------------------------------------------ */

export function RuleBuilder({ rules, onChange }: RuleBuilderProps) {
  const addRule = () => {
    onChange([...rules, { resources: [], verbs: [], resourceNames: [] }])
  }

  const updateRule = (index: number, rule: Rule) => {
    const next = [...rules]
    next[index] = rule
    onChange(next)
  }

  const removeRule = (index: number) => {
    onChange(rules.filter((_, i) => i !== index))
  }

  return (
    <div className="space-y-3">
      {rules.map((rule, idx) => (
        <RuleRow
          key={idx}
          rule={rule}
          index={idx}
          canRemove={rules.length > 1}
          onChange={(r) => updateRule(idx, r)}
          onRemove={() => removeRule(idx)}
        />
      ))}

      <button
        type="button"
        onClick={addRule}
        className="inline-flex items-center gap-1.5 rounded-md border border-dashed px-3 py-2 text-sm text-muted-foreground transition-colors hover:border-primary hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <Plus className="h-3.5 w-3.5" />
        Add Rule
      </button>
    </div>
  )
}
