import { useEffect, useMemo, useState } from 'react'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

type ToolAccessMode = 'unrestricted' | 'allowlist' | 'denylist'

interface AgentPolicySpec {
  tool_access?: {
    mode: ToolAccessMode
    tools?: string[]
  }
  budget?: {
    max_usd?: number
    max_tokens?: number
  }
  sandbox?: {
    minimum_tier?: string
  }
}

interface AgentPolicyEditorProps {
  value: AgentPolicySpec
  onChange: (value: AgentPolicySpec) => void
}

/* ------------------------------------------------------------------ */
/* Sandbox tier options                                                 */
/* ------------------------------------------------------------------ */

const SANDBOX_TIERS = [
  { value: 'none', label: 'None' },
  { value: 'wasm', label: 'WebAssembly (WASM)' },
  { value: 'docker', label: 'Docker container' },
  { value: 'microvm', label: 'Micro VM' },
] as const

/* ------------------------------------------------------------------ */
/* Component                                                           */
/* ------------------------------------------------------------------ */

export function AgentPolicyEditor({ value, onChange }: AgentPolicyEditorProps) {
  const fetchResources = useResourceStore((s) => s.fetchResources)
  const toolResources = useResourceStore((s) => s.resources['tools'] ?? [])

  const [loadedTools, setLoadedTools] = useState(false)

  useEffect(() => {
    if (!loadedTools) {
      void fetchResources('tools')
      setLoadedTools(true)
    }
  }, [loadedTools, fetchResources])

  const toolNames = useMemo(
    () => toolResources.map((t: Resource) => t.metadata.name),
    [toolResources],
  )

  const toolMode: ToolAccessMode = value.tool_access?.mode ?? 'unrestricted'
  const selectedTools: string[] = value.tool_access?.tools ?? []
  const maxUsd = value.budget?.max_usd ?? 0
  const maxTokens = value.budget?.max_tokens ?? 0
  const sandboxTier = value.sandbox?.minimum_tier ?? 'none'

  const updateToolAccess = (mode: ToolAccessMode, tools?: string[]) => {
    onChange({
      ...value,
      tool_access: {
        mode,
        ...(mode !== 'unrestricted' && tools ? { tools } : {}),
      },
    })
  }

  const toggleTool = (tool: string) => {
    const next = selectedTools.includes(tool)
      ? selectedTools.filter((t) => t !== tool)
      : [...selectedTools, tool]
    updateToolAccess(toolMode, next)
  }

  const updateBudget = (field: 'max_usd' | 'max_tokens', val: number) => {
    onChange({
      ...value,
      budget: {
        ...value.budget,
        [field]: val || undefined,
      },
    })
  }

  const updateSandbox = (tier: string) => {
    onChange({
      ...value,
      sandbox: { minimum_tier: tier },
    })
  }

  return (
    <div className="space-y-6">
      {/* Tool access */}
      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Tool Access</legend>
        <div className="space-y-3">
          <div>
            <label htmlFor="tool-access-mode" className="mb-1 block text-xs text-muted-foreground">
              Mode
            </label>
            <select
              id="tool-access-mode"
              value={toolMode}
              onChange={(e) => updateToolAccess(e.target.value as ToolAccessMode, selectedTools)}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <option value="unrestricted">Unrestricted</option>
              <option value="allowlist">Allowlist</option>
              <option value="denylist">Denylist</option>
            </select>
          </div>

          {toolMode !== 'unrestricted' && (
            <div>
              <p className="mb-1.5 text-xs text-muted-foreground">
                {toolMode === 'allowlist'
                  ? 'Select tools the agent CAN use'
                  : 'Select tools the agent CANNOT use'}
              </p>
              {toolNames.length === 0 ? (
                <p className="text-xs text-muted-foreground/60">
                  No tools found. Create tools first.
                </p>
              ) : (
                <div className="flex max-h-40 flex-wrap gap-1.5 overflow-y-auto rounded-md border bg-background p-2">
                  {toolNames.map((tool) => {
                    const checked = selectedTools.includes(tool)
                    return (
                      <label
                        key={tool}
                        className={`inline-flex cursor-pointer items-center gap-1 rounded-md border px-2 py-1 text-xs transition-colors ${
                          checked
                            ? 'border-primary/40 bg-primary/10 text-primary'
                            : 'border-border text-muted-foreground hover:bg-muted'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleTool(tool)}
                          className="sr-only"
                          aria-label={`Tool: ${tool}`}
                        />
                        {tool}
                      </label>
                    )
                  })}
                </div>
              )}
            </div>
          )}
        </div>
      </fieldset>

      {/* Budget */}
      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Budget</legend>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label htmlFor="budget-max-usd" className="mb-1 block text-xs text-muted-foreground">
              Max USD
            </label>
            <div className="flex items-center gap-2">
              <input
                id="budget-max-usd"
                type="range"
                min={0}
                max={100}
                step={0.5}
                value={maxUsd}
                onChange={(e) => updateBudget('max_usd', parseFloat(e.target.value))}
                className="flex-1"
                aria-label="Maximum USD budget"
              />
              <input
                type="number"
                min={0}
                step={0.5}
                value={maxUsd || ''}
                onChange={(e) => updateBudget('max_usd', parseFloat(e.target.value) || 0)}
                placeholder="0"
                className="w-20 rounded-md border bg-background px-2 py-1 text-right text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Maximum USD budget value"
              />
            </div>
            {maxUsd > 0 && (
              <p className="mt-0.5 text-xs text-muted-foreground">${maxUsd.toFixed(2)} limit</p>
            )}
          </div>

          <div>
            <label htmlFor="budget-max-tokens" className="mb-1 block text-xs text-muted-foreground">
              Max Tokens
            </label>
            <div className="flex items-center gap-2">
              <input
                id="budget-max-tokens"
                type="range"
                min={0}
                max={1000000}
                step={10000}
                value={maxTokens}
                onChange={(e) => updateBudget('max_tokens', parseInt(e.target.value))}
                className="flex-1"
                aria-label="Maximum token budget"
              />
              <input
                type="number"
                min={0}
                step={10000}
                value={maxTokens || ''}
                onChange={(e) => updateBudget('max_tokens', parseInt(e.target.value) || 0)}
                placeholder="0"
                className="w-24 rounded-md border bg-background px-2 py-1 text-right text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Maximum token budget value"
              />
            </div>
            {maxTokens > 0 && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {maxTokens.toLocaleString()} tokens
              </p>
            )}
          </div>
        </div>
      </fieldset>

      {/* Sandbox */}
      <fieldset>
        <legend className="mb-2 text-sm font-semibold">Sandbox</legend>
        <div>
          <label
            htmlFor="sandbox-minimum-tier"
            className="mb-1 block text-xs text-muted-foreground"
          >
            Minimum tier
          </label>
          <select
            id="sandbox-minimum-tier"
            value={sandboxTier}
            onChange={(e) => updateSandbox(e.target.value)}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:w-auto"
          >
            {SANDBOX_TIERS.map((tier) => (
              <option key={tier.value} value={tier.value}>
                {tier.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-xs text-muted-foreground">
            Agents bound to this policy require at least this sandbox level.
          </p>
        </div>
      </fieldset>
    </div>
  )
}
