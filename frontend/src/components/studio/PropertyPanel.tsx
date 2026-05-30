import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  createContext,
  useContext,
  type ChangeEvent,
} from 'react'
import { useShallow } from 'zustand/react/shallow'
import * as Tabs from '@radix-ui/react-tabs'
import { X, Trash2, Play, ChevronDown, ChevronRight, Copy, Check } from 'lucide-react'
import { CodeBlock } from '@/components/ui/CodeBlock'
import { Link } from 'react-router-dom'
import { useStudioStore } from '@/stores/studioStore'
import { useResourceStore } from '@/stores/resourceStore'
import type { Resource } from '@/lib/types'
import { modKey } from '@/lib/platform'
import { nodeToYaml } from './nodeYaml'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'
import { ExpressionEditor } from './ExpressionEditor'
import { Spinner } from '@/components/ui/Spinner'
import { api } from '@/api/client'
import { getErrorMessage } from '@/lib/utils'
import { useCopyToClipboard } from '@/hooks'

/** Context providing a generated field id from the enclosing FieldGroup */
const FieldIdContext = createContext<string>('')

function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label
      htmlFor={htmlFor}
      className="mb-1 block text-xs font-semibold tracking-wide text-muted-foreground"
    >
      {children}
    </label>
  )
}

function TextInput({
  value,
  onChange,
  placeholder,
  multiline,
}: {
  value: string
  onChange: (v: string) => void
  placeholder?: string
  multiline?: boolean
}) {
  const fieldId = useContext(FieldIdContext)
  const cls =
    'w-full text-xs text-foreground bg-background border border-border rounded-md px-2.5 py-1.5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring placeholder:text-muted-foreground/50 resize-none transition-colors'

  if (multiline) {
    return (
      <textarea
        id={fieldId || undefined}
        className={cls}
        rows={3}
        value={value}
        placeholder={placeholder}
        autoComplete="off"
        onChange={(e: ChangeEvent<HTMLTextAreaElement>) => onChange(e.target.value)}
      />
    )
  }

  return (
    <input
      id={fieldId || undefined}
      type="text"
      className={cls}
      value={value}
      placeholder={placeholder}
      autoComplete="off"
      onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.value)}
    />
  )
}

function SelectInput({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { label: string; value: string }[]
}) {
  const fieldId = useContext(FieldIdContext)
  return (
    <select
      id={fieldId || undefined}
      className="w-full rounded-md border border-border bg-background px-2.5 py-1.5 text-xs text-foreground transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      value={value}
      onChange={(e: ChangeEvent<HTMLSelectElement>) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  )
}

function CheckboxInput({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex min-h-[44px] cursor-pointer items-center gap-2 sm:min-h-0">
      <input
        type="checkbox"
        className="h-3.5 w-3.5 rounded border-border accent-primary"
        checked={checked}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
      />
      <span className="text-xs text-foreground">{label}</span>
    </label>
  )
}

function FieldGroup({ label, children }: { label: string; children: React.ReactNode }) {
  const fieldId = `panel-${label.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
  return (
    <FieldIdContext.Provider value={fieldId}>
      <div className="space-y-1">
        <Label htmlFor={fieldId}>{label}</Label>
        {children}
      </div>
    </FieldIdContext.Provider>
  )
}

const EMPTY_RESOURCES: Resource[] = []

function LLMSelect({
  value,
  onChange,
  connections,
}: {
  value: string
  onChange: (v: string) => void
  connections: Resource[]
}) {
  const options = useMemo(
    () => [
      { value: '', label: 'Select LLM connection...' },
      ...connections.map((conn) => {
        const model = (conn.spec.model as string | undefined) ?? ''
        return {
          value: `ref:llm-connections/${conn.metadata.name}`,
          label: model ? `${conn.metadata.name} (${model})` : conn.metadata.name,
        }
      }),
    ],
    [connections],
  )
  return <SelectInput value={value} onChange={onChange} options={options} />
}

const str = (data: Record<string, unknown>, key: string) => (data[key] as string | undefined) ?? ''
const bool = (data: Record<string, unknown>, key: string) =>
  (data[key] as boolean | undefined) ?? false

function AgentForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const llmConnections =
    useResourceStore((state) => state.resources['llm-connections']) ?? EMPTY_RESOURCES
  const hasLlmData = useResourceStore((state) => 'llm-connections' in state.resources)
  const fetchResources = useResourceStore((state) => state.fetchResources)

  useEffect(() => {
    if (!hasLlmData) void fetchResources('llm-connections')
  }, [hasLlmData, fetchResources])

  return (
    <div className="space-y-3">
      <FieldGroup label="Role">
        <TextInput
          value={str(data, 'role')}
          onChange={(v) => onChange('role', v)}
          placeholder="Senior Researcher"
        />
      </FieldGroup>
      <FieldGroup label="Goal">
        <TextInput
          value={str(data, 'goal')}
          onChange={(v) => onChange('goal', v)}
          placeholder="What should this agent achieve?"
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Backstory">
        <TextInput
          value={str(data, 'backstory')}
          onChange={(v) => onChange('backstory', v)}
          placeholder="Agent background and expertise..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="LLM">
        {llmConnections.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No LLM connections configured.{' '}
            <Link to="/models" className="text-primary underline">
              Add one in Models →
            </Link>
          </p>
        ) : (
          <LLMSelect
            value={str(data, 'llm')}
            onChange={(v) => onChange('llm', v)}
            connections={llmConnections}
          />
        )}
      </FieldGroup>
      <CheckboxInput
        label="Verbose"
        checked={bool(data, 'verbose')}
        onChange={(v) => onChange('verbose', v)}
      />
      <NodeTestSection nodeType="agent" data={data} />
    </div>
  )
}

function TaskForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const agentNodes = useStudioStore(
    useShallow((state) => state.nodes.filter((n) => n.type === 'agent')),
  )

  const agentOptions = useMemo(
    () => [
      { value: '', label: 'Select agent...' },
      ...agentNodes.map((node) => {
        const nodeData = node.data
        const role = (nodeData.role as string | undefined) ?? ''
        const kebabName =
          (nodeData.name as string | undefined) ||
          role
            .toLowerCase()
            .replace(/\s+/g, '-')
            .replace(/[^a-z0-9-]/g, '')
        return {
          value: `ref:agents/${kebabName}`,
          label: role || node.id,
        }
      }),
    ],
    [agentNodes],
  )

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="research_topic"
        />
      </FieldGroup>
      <FieldGroup label="Description">
        <TextInput
          value={str(data, 'description')}
          onChange={(v) => onChange('description', v)}
          placeholder="Describe what this task does..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Expected Output">
        <TextInput
          value={str(data, 'expected_output')}
          onChange={(v) => onChange('expected_output', v)}
          placeholder="A detailed report on..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Agent">
        <SelectInput
          value={str(data, 'agent')}
          onChange={(v) => onChange('agent', v)}
          options={agentOptions}
        />
      </FieldGroup>
      <NodeTestSection nodeType="task" data={data} />
    </div>
  )
}

function ToolForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="web_search_tool"
        />
      </FieldGroup>
      <FieldGroup label="Type">
        <SelectInput
          value={str(data, 'type') || 'python'}
          onChange={(v) => onChange('type', v)}
          options={[
            { label: 'Python', value: 'python' },
            { label: 'WebAssembly', value: 'wasm' },
            { label: 'Built-in', value: 'builtin' },
          ]}
        />
      </FieldGroup>
      <FieldGroup label="Class Path">
        <TextInput
          value={str(data, 'class_path')}
          onChange={(v) => onChange('class_path', v)}
          placeholder="my_module.MyTool"
        />
      </FieldGroup>
      <FieldGroup label="Description">
        <TextInput
          value={str(data, 'description')}
          onChange={(v) => onChange('description', v)}
          placeholder="What does this tool do?"
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Sandbox">
        <SelectInput
          value={str(data, 'sandbox') || 'none'}
          onChange={(v) => onChange('sandbox', v)}
          options={[
            { label: 'No sandbox', value: 'none' },
            { label: 'WebAssembly (WASM)', value: 'wasm' },
          ]}
        />
      </FieldGroup>
    </div>
  )
}

function FlowStepForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const crewResources = useResourceStore((state) => state.resources['crews']) ?? EMPTY_RESOURCES
  const hasCrewData = useResourceStore((state) => 'crews' in state.resources)
  const fetchResources = useResourceStore((state) => state.fetchResources)

  const flowStepNodes = useStudioStore(
    useShallow((state) => state.nodes.filter((n) => n.type === 'flowStep')),
  )

  useEffect(() => {
    if (!hasCrewData) void fetchResources('crews')
  }, [hasCrewData, fetchResources])

  const stepType = str(data, 'type') || 'crew'
  const listenTo = (data['listen_to'] as string[] | undefined) ?? []
  const currentName = str(data, 'name')

  const otherStepNames = useMemo(
    () =>
      flowStepNodes
        .map((n) => (n.data['name'] as string | undefined) ?? '')
        .filter((n) => n && n !== currentName),
    [flowStepNodes, currentName],
  )

  const crewOptions = useMemo(
    () => [
      { value: '', label: 'Select crew...' },
      ...crewResources.map((c) => ({
        value: `ref:crews/${c.metadata.name}`,
        label: c.metadata.name,
      })),
    ],
    [crewResources],
  )

  return (
    <div className="space-y-3">
      <FieldGroup label="Step Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="step-1"
        />
      </FieldGroup>
      <FieldGroup label="Type">
        <SelectInput
          value={stepType}
          onChange={(v) => onChange('type', v)}
          options={[
            { label: 'Crew', value: 'crew' },
            { label: 'Function', value: 'function' },
            { label: 'Router', value: 'router' },
            { label: 'Condition', value: 'condition' },
          ]}
        />
      </FieldGroup>

      {stepType === 'crew' && (
        <FieldGroup label="Crew">
          {crewResources.length === 0 ? (
            <p className="text-xs text-muted-foreground">No crews saved yet.</p>
          ) : (
            <SelectInput
              value={str(data, 'crew')}
              onChange={(v) => onChange('crew', v)}
              options={crewOptions}
            />
          )}
        </FieldGroup>
      )}

      {stepType === 'function' && (
        <FieldGroup label="Function Path">
          <TextInput
            value={str(data, 'function_path')}
            onChange={(v) => onChange('function_path', v)}
            placeholder="my_module.my_function"
          />
        </FieldGroup>
      )}

      {otherStepNames.length > 0 && (
        <FieldGroup label="Listen To">
          <div className="space-y-1">
            {otherStepNames.map((stepName) => (
              <CheckboxInput
                key={stepName}
                label={stepName}
                checked={listenTo.includes(stepName)}
                onChange={(checked) => {
                  const next = checked
                    ? [...listenTo, stepName]
                    : listenTo.filter((s) => s !== stepName)
                  onChange('listen_to', next)
                }}
              />
            ))}
          </div>
        </FieldGroup>
      )}
    </div>
  )
}

const PII_PRESETS: Record<string, { label: string; entities: string[] }> = {
  hipaa: {
    label: 'HIPAA',
    entities: [
      'PERSON',
      'DATE_TIME',
      'US_SSN',
      'PHONE_NUMBER',
      'EMAIL_ADDRESS',
      'LOCATION',
      'IP_ADDRESS',
      'MEDICAL_LICENSE',
      'US_DRIVER_LICENSE',
    ],
  },
  gdpr: {
    label: 'GDPR',
    entities: [
      'PERSON',
      'EMAIL_ADDRESS',
      'PHONE_NUMBER',
      'LOCATION',
      'IP_ADDRESS',
      'DATE_TIME',
      'IBAN_CODE',
      'NRP',
    ],
  },
  'pci-dss': {
    label: 'PCI-DSS',
    entities: ['CREDIT_CARD', 'IBAN_CODE', 'US_BANK_NUMBER', 'PERSON'],
  },
  ccpa: {
    label: 'CCPA',
    entities: [
      'PERSON',
      'EMAIL_ADDRESS',
      'PHONE_NUMBER',
      'LOCATION',
      'IP_ADDRESS',
      'US_SSN',
      'US_DRIVER_LICENSE',
      'CREDIT_CARD',
    ],
  },
}

const ALL_PII_ENTITIES = [
  'PERSON',
  'EMAIL_ADDRESS',
  'PHONE_NUMBER',
  'CREDIT_CARD',
  'US_SSN',
  'IP_ADDRESS',
  'LOCATION',
  'DATE_TIME',
  'IBAN_CODE',
  'US_BANK_NUMBER',
  'US_DRIVER_LICENSE',
  'MEDICAL_LICENSE',
  'NRP',
] as const

function PIIForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const entities = (data['entities'] as string[] | undefined) ?? []
  const preset = (data['preset'] as string | undefined) ?? 'custom'
  const backend = str(data, 'backend') || 'default'

  const handlePresetChange = (newPreset: string) => {
    onChange('preset', newPreset)
    if (newPreset !== 'custom' && PII_PRESETS[newPreset]) {
      onChange('entities', PII_PRESETS[newPreset].entities)
    }
  }

  return (
    <div className="space-y-3">
      <FieldGroup label="Compliance Preset">
        <SelectInput
          value={preset}
          onChange={handlePresetChange}
          options={[
            { label: 'Custom', value: 'custom' },
            { label: 'HIPAA', value: 'hipaa' },
            { label: 'GDPR', value: 'gdpr' },
            { label: 'PCI-DSS', value: 'pci-dss' },
            { label: 'CCPA', value: 'ccpa' },
          ]}
        />
        {preset !== 'custom' && PII_PRESETS[preset] && (
          <p className="mt-1 text-[10px] text-muted-foreground">
            {PII_PRESETS[preset].entities.length} entities selected by {PII_PRESETS[preset].label}{' '}
            standard
          </p>
        )}
      </FieldGroup>
      <FieldGroup label="Entities">
        <div className="space-y-1">
          {ALL_PII_ENTITIES.map((entity) => (
            <CheckboxInput
              key={entity}
              label={entity.replace(/_/g, ' ')}
              checked={entities.includes(entity)}
              onChange={(checked) => {
                const next = checked ? [...entities, entity] : entities.filter((e) => e !== entity)
                onChange('entities', next)
                onChange('preset', 'custom')
              }}
            />
          ))}
        </div>
      </FieldGroup>
      <FieldGroup label="Action">
        <SelectInput
          value={str(data, 'action') || 'redact'}
          onChange={(v) => onChange('action', v)}
          options={[
            { label: 'Redact', value: 'redact' },
            { label: 'Reject', value: 'reject' },
            { label: 'Warn', value: 'warn' },
          ]}
        />
      </FieldGroup>
      <FieldGroup label="Backend">
        <SelectInput
          value={backend}
          onChange={(v) => onChange('backend', v)}
          options={[
            { label: 'Default', value: 'default' },
            { label: 'Presidio NLP', value: 'presidio-nlp' },
            { label: 'LiteLLM', value: 'litellm' },
          ]}
        />
      </FieldGroup>
      {backend === 'litellm' && (
        <FieldGroup label="Model">
          <TextInput
            value={str(data, 'model')}
            onChange={(v) => onChange('model', v)}
            placeholder="gpt-4o-mini"
          />
        </FieldGroup>
      )}
    </div>
  )
}

function ConditionForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const flowStepNodes = useStudioStore(
    useShallow((state) =>
      state.nodes.filter(
        (n) =>
          n.type === 'flowStep' ||
          n.type === 'condition' ||
          n.type === 'router' ||
          n.type === 'parallel',
      ),
    ),
  )

  const currentName = str(data, 'name')
  const otherStepNames = useMemo(
    () =>
      flowStepNodes
        .map((n) => (n.data['name'] as string | undefined) ?? '')
        .filter((n) => n && n !== currentName),
    [flowStepNodes, currentName],
  )

  const branchOptions = useMemo(
    () => [
      { value: '', label: 'Select step...' },
      ...otherStepNames.map((n) => ({ value: n, label: n })),
    ],
    [otherStepNames],
  )

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="check-condition"
        />
      </FieldGroup>
      <FieldGroup label="Condition">
        <ExpressionEditor
          value={str(data, 'condition')}
          onChange={(v) => onChange('condition', v)}
          placeholder="state.status == 'approved'"
        />
      </FieldGroup>
      <FieldGroup label="True Branch">
        <SelectInput
          value={str(data, 'true_branch')}
          onChange={(v) => onChange('true_branch', v)}
          options={branchOptions}
        />
      </FieldGroup>
      <FieldGroup label="False Branch">
        <SelectInput
          value={str(data, 'false_branch')}
          onChange={(v) => onChange('false_branch', v)}
          options={branchOptions}
        />
      </FieldGroup>
    </div>
  )
}

function RouterForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const routes = useMemo(() => (data['routes'] as Record<string, string> | undefined) ?? {}, [data])
  const entries = Object.entries(routes)

  const addRoute = useCallback(() => {
    const next = { ...routes, '': '' }
    onChange('routes', next)
  }, [routes, onChange])

  const updateRouteKey = useCallback(
    (oldKey: string, newKey: string) => {
      const next: Record<string, string> = {}
      for (const [k, v] of Object.entries(routes)) {
        next[k === oldKey ? newKey : k] = v
      }
      onChange('routes', next)
    },
    [routes, onChange],
  )

  const updateRouteValue = useCallback(
    (key: string, value: string) => {
      onChange('routes', { ...routes, [key]: value })
    },
    [routes, onChange],
  )

  const removeRoute = useCallback(
    (key: string) => {
      const next = { ...routes }
      delete next[key]
      onChange('routes', next)
    },
    [routes, onChange],
  )

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="route-step"
        />
      </FieldGroup>
      <div className="space-y-1">
        <Label>Routes</Label>
        {entries.map(([condition, target], idx) => (
          <div key={idx} className="space-y-1 rounded-md border border-border bg-muted/20 p-2">
            <div>
              <label className="text-[10px] font-medium text-muted-foreground">
                Condition
                <ExpressionEditor
                  value={condition}
                  onChange={(v) => updateRouteKey(condition, v)}
                  placeholder="state.status == 'approved'"
                />
              </label>
            </div>
            <div>
              <label className="text-[10px] font-medium text-muted-foreground">
                Target step
                <input
                  type="text"
                  className="mt-0.5 w-full rounded-md border border-border bg-background px-2 py-1 text-xs text-foreground placeholder:text-muted-foreground/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  value={target}
                  placeholder="target"
                  onChange={(e) => updateRouteValue(condition, e.target.value)}
                />
              </label>
            </div>
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => removeRoute(condition)}
                className="shrink-0 rounded p-1 text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Remove route"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
        ))}
        <button
          type="button"
          onClick={addRoute}
          className="text-xs font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          + Add route
        </button>
      </div>
    </div>
  )
}

function ParallelForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const flowStepNodes = useStudioStore(
    useShallow((state) =>
      state.nodes.filter(
        (n) =>
          n.type === 'flowStep' ||
          n.type === 'condition' ||
          n.type === 'router' ||
          n.type === 'parallel',
      ),
    ),
  )

  const currentName = str(data, 'name')
  const branches = (data['branches'] as string[] | undefined) ?? []

  const otherStepNames = useMemo(
    () =>
      flowStepNodes
        .map((n) => (n.data['name'] as string | undefined) ?? '')
        .filter((n) => n && n !== currentName),
    [flowStepNodes, currentName],
  )

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="parallel-exec"
        />
      </FieldGroup>
      {otherStepNames.length > 0 && (
        <FieldGroup label="Branches">
          <div className="space-y-1">
            {otherStepNames.map((stepName) => (
              <CheckboxInput
                key={stepName}
                label={stepName}
                checked={branches.includes(stepName)}
                onChange={(checked) => {
                  const next = checked
                    ? [...branches, stepName]
                    : branches.filter((s) => s !== stepName)
                  onChange('branches', next)
                }}
              />
            ))}
          </div>
        </FieldGroup>
      )}
    </div>
  )
}

function CrewGroupForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Crew Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="research-crew"
        />
      </FieldGroup>
    </div>
  )
}

const STICKY_COLORS = [
  { value: 'yellow', label: 'Yellow', swatch: 'bg-amber-300' },
  { value: 'blue', label: 'Blue', swatch: 'bg-sky-300' },
  { value: 'green', label: 'Green', swatch: 'bg-emerald-300' },
  { value: 'pink', label: 'Pink', swatch: 'bg-pink-300' },
] as const

function StickyNoteForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const currentColor = (data['color'] as string | undefined) ?? 'yellow'
  return (
    <div className="space-y-3">
      <FieldGroup label="Text">
        <TextInput
          value={str(data, 'text')}
          onChange={(v) => onChange('text', v)}
          placeholder="Write a note..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Color">
        <div className="flex gap-2">
          {STICKY_COLORS.map((c) => (
            <button
              key={c.value}
              type="button"
              onClick={() => onChange('color', c.value)}
              aria-label={c.label}
              aria-pressed={currentColor === c.value}
              className={`h-6 w-6 rounded-full border-2 transition-all ${c.swatch} ${
                currentColor === c.value
                  ? 'scale-110 border-foreground'
                  : 'border-transparent hover:border-muted-foreground/40'
              }`}
            />
          ))}
        </div>
      </FieldGroup>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Logic Block Forms                                                    */
/* ------------------------------------------------------------------ */

function IfElseForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="check-quality"
        />
      </FieldGroup>
      <FieldGroup label="Condition Expression">
        <TextInput
          value={str(data, 'condition')}
          onChange={(v) => onChange('condition', v)}
          placeholder="score >= 0.8"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          Supports: ==, !=, &gt;, &lt;, &gt;=, &lt;=, in. Variables from upstream outputs.
        </p>
      </FieldGroup>
      <FieldGroup label="True Branch Label">
        <TextInput
          value={str(data, 'true_label') || 'True'}
          onChange={(v) => onChange('true_label', v)}
        />
      </FieldGroup>
      <FieldGroup label="False Branch Label">
        <TextInput
          value={str(data, 'false_label') || 'False'}
          onChange={(v) => onChange('false_label', v)}
        />
      </FieldGroup>
    </div>
  )
}

function SwitchForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const cases = (data['cases'] as string[] | undefined) ?? []
  const [newCase, setNewCase] = useState('')

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="route-by-type"
        />
      </FieldGroup>
      <FieldGroup label="Expression">
        <TextInput
          value={str(data, 'expression')}
          onChange={(v) => onChange('expression', v)}
          placeholder="result.category"
        />
      </FieldGroup>
      <FieldGroup label={`Cases (${cases.length})`}>
        <div className="space-y-1">
          {cases.map((c, i) => (
            <div key={i} className="flex items-center gap-1">
              <span className="flex-1 truncate rounded border bg-muted/30 px-2 py-1 text-xs">
                {c}
              </span>
              <button
                type="button"
                onClick={() =>
                  onChange(
                    'cases',
                    cases.filter((_, j) => j !== i),
                  )
                }
                className="rounded p-1 text-xs text-muted-foreground hover:text-destructive"
                aria-label={`Remove case ${c}`}
              >
                ×
              </button>
            </div>
          ))}
          <div className="flex gap-1">
            <input
              type="text"
              value={newCase}
              onChange={(e) => setNewCase(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && newCase.trim()) {
                  onChange('cases', [...cases, newCase.trim()])
                  setNewCase('')
                }
              }}
              placeholder="Add case…"
              className="flex-1 rounded border bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            />
            <button
              type="button"
              onClick={() => {
                if (newCase.trim()) {
                  onChange('cases', [...cases, newCase.trim()])
                  setNewCase('')
                }
              }}
              className="rounded bg-primary px-2 py-1 text-xs text-primary-foreground"
            >
              Add
            </button>
          </div>
        </div>
      </FieldGroup>
    </div>
  )
}

function MergeForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="merge-results"
        />
      </FieldGroup>
      <FieldGroup label="Input Count">
        <input
          type="number"
          min={2}
          max={10}
          value={(data['input_count'] as number | undefined) ?? 2}
          onChange={(e) => onChange('input_count', parseInt(e.target.value, 10) || 2)}
          className="w-full rounded border bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </FieldGroup>
      <FieldGroup label="Strategy">
        <SelectInput
          value={str(data, 'strategy') || 'wait_all'}
          onChange={(v) => onChange('strategy', v)}
          options={[
            { label: 'Wait for all inputs', value: 'wait_all' },
            { label: 'First input wins', value: 'first' },
          ]}
        />
      </FieldGroup>
    </div>
  )
}

function FilterForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="filter-results"
        />
      </FieldGroup>
      <FieldGroup label="Filter Condition">
        <TextInput
          value={str(data, 'condition')}
          onChange={(v) => onChange('condition', v)}
          placeholder="item.score > 0.5"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          Items matching go to &quot;Passed&quot; port, others to &quot;Rejected&quot;.
        </p>
      </FieldGroup>
    </div>
  )
}

function GateForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="quality-gate"
        />
      </FieldGroup>
      <FieldGroup label="Control Expression">
        <TextInput
          value={str(data, 'control')}
          onChange={(v) => onChange('control', v)}
          placeholder="approval_status == approved"
        />
      </FieldGroup>
      <FieldGroup label="Pass When">
        <SelectInput
          value={str(data, 'pass_when') || 'true'}
          onChange={(v) => onChange('pass_when', v)}
          options={[
            { label: 'Control is True', value: 'true' },
            { label: 'Control is False', value: 'false' },
          ]}
        />
      </FieldGroup>
    </div>
  )
}

function LoopForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput
          value={str(data, 'name')}
          onChange={(v) => onChange('name', v)}
          placeholder="process-items"
        />
      </FieldGroup>
      <FieldGroup label="Items Expression">
        <TextInput
          value={str(data, 'items_expr')}
          onChange={(v) => onChange('items_expr', v)}
          placeholder="results.items"
        />
        <p className="mt-1 text-[10px] text-muted-foreground">
          Expression that resolves to a list. Each item is passed to the connected subgraph.
        </p>
      </FieldGroup>
      <FieldGroup label="Max Iterations">
        <input
          type="number"
          min={1}
          max={1000}
          value={(data['max_iterations'] as number | undefined) ?? 100}
          onChange={(e) => onChange('max_iterations', parseInt(e.target.value, 10) || 100)}
          className="w-full rounded border bg-background px-2 py-1 text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
        />
      </FieldGroup>
      <FieldGroup label="Parallel">
        <CheckboxInput
          label="Execute iterations in parallel"
          checked={(data['parallel'] as boolean | undefined) ?? false}
          onChange={(v) => onChange('parallel', v)}
        />
      </FieldGroup>
    </div>
  )
}

function CrewComponentForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  return (
    <div className="space-y-3">
      <FieldGroup label="Crew Name">
        <TextInput
          value={str(data, 'crew_name')}
          onChange={(v) => onChange('crew_name', v)}
          placeholder="research-crew"
        />
      </FieldGroup>
      <FieldGroup label="Description">
        <TextInput
          value={str(data, 'description')}
          onChange={(v) => onChange('description', v)}
          placeholder="Researches topics and produces reports"
        />
      </FieldGroup>
      <FieldGroup label="Info">
        <div className="flex gap-2 text-[10px] text-muted-foreground">
          <span>{(data['agent_count'] as number) ?? 0} agents</span>
          <span>{(data['task_count'] as number) ?? 0} tasks</span>
        </div>
        <p className="mt-1 text-[10px] text-muted-foreground">
          Double-click the node on canvas to drill into the crew&apos;s internal graph.
        </p>
      </FieldGroup>
    </div>
  )
}

interface ChatResponse {
  content: string
}

interface ModelInfo {
  name: string
}

function NodeTestSection({
  nodeType,
  data,
}: {
  nodeType: 'agent' | 'task'
  data: Record<string, unknown>
}) {
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<string | null>(null)
  const [expanded, setExpanded] = useState(true)
  const { copied, copy } = useCopyToClipboard()

  const handleTest = async () => {
    setTesting(true)
    setResult(null)
    try {
      const models = await api.get<ModelInfo[]>('/api/v1/models/available')
      if (models.length === 0) {
        setResult('Error: No models available. Configure an LLM connection first.')
        setExpanded(true)
        return
      }

      const model = models[0]!.name
      const messages: { role: string; content: string }[] = []

      if (nodeType === 'agent') {
        const role = str(data, 'role')
        const goal = str(data, 'goal')
        const backstory = str(data, 'backstory')
        const systemParts = [
          role && `You are a ${role}.`,
          goal && `Your goal: ${goal}`,
          backstory && `Background: ${backstory}`,
        ].filter(Boolean)
        if (systemParts.length > 0) {
          messages.push({ role: 'system', content: systemParts.join(' ') })
        }
        messages.push({ role: 'user', content: 'Introduce yourself briefly.' })
      } else {
        const description = str(data, 'description')
        const expectedOutput = str(data, 'expected_output')
        const prompt = [
          description && `Task: ${description}`,
          expectedOutput && `Expected output format: ${expectedOutput}`,
          'Provide a brief sample output for this task.',
        ]
          .filter(Boolean)
          .join('\n')
        messages.push({ role: 'user', content: prompt })
      }

      const resp = await api.post<ChatResponse>('/api/v1/chat', {
        model,
        messages,
        max_tokens: 150,
      })
      setResult(resp.content)
      setExpanded(true)
    } catch (err: unknown) {
      setResult(`Error: ${getErrorMessage(err, 'Test failed')}`)
      setExpanded(true)
    } finally {
      setTesting(false)
    }
  }

  const handleCopy = () => {
    if (!result) return
    void copy(result)
  }

  const hasEnoughData =
    nodeType === 'agent'
      ? Boolean(str(data, 'role') || str(data, 'goal'))
      : Boolean(str(data, 'description'))

  return (
    <div className="mt-4 border-t border-border pt-4">
      <button
        type="button"
        disabled={testing || !hasEnoughData}
        onClick={() => void handleTest()}
        className="inline-flex w-full items-center justify-center gap-1.5 rounded-md bg-primary px-3 py-2 text-xs font-medium text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
      >
        {testing ? <Spinner size="sm" className="text-current" /> : <Play className="h-3 w-3" />}
        {testing ? 'Testing...' : `Test ${nodeType === 'agent' ? 'Agent' : 'Task'}`}
      </button>
      {!hasEnoughData && (
        <p className="text-2xs mt-1.5 text-center text-muted-foreground">
          {nodeType === 'agent' ? 'Add a role or goal first' : 'Add a description first'}
        </p>
      )}
      {result !== null && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="mb-1.5 flex w-full items-center gap-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            {expanded ? <ChevronDown className="h-3 w-3" /> : <ChevronRight className="h-3 w-3" />}
            Test Result
          </button>
          {expanded && (
            <div className="relative rounded-md border bg-muted/30 p-2.5">
              <button
                type="button"
                onClick={handleCopy}
                className="absolute right-1.5 top-1.5 rounded p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                aria-label="Copy result"
              >
                {copied ? (
                  <Check className="h-3 w-3 text-emerald-500" />
                ) : (
                  <Copy className="h-3 w-3" />
                )}
              </button>
              <pre className="text-2xs max-h-48 overflow-auto whitespace-pre-wrap pr-6 font-mono leading-relaxed text-foreground">
                {result}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

const TYPE_META: Record<string, { label: string; accent: string; border: string }> = {
  agent: { label: 'Agent', accent: 'bg-violet-500', border: 'border-violet-200' },
  task: { label: 'Task', accent: 'bg-blue-500', border: 'border-blue-200' },
  tool: { label: 'Tool', accent: 'bg-emerald-500', border: 'border-emerald-200' },
  flowStep: { label: 'Flow Step', accent: 'bg-amber-500', border: 'border-amber-200' },
  pii: { label: 'PII Redaction', accent: 'bg-rose-500', border: 'border-rose-200' },
  condition: { label: 'Condition', accent: 'bg-amber-500', border: 'border-amber-200' },
  router: { label: 'Router', accent: 'bg-cyan-500', border: 'border-cyan-200' },
  parallel: { label: 'Parallel', accent: 'bg-purple-500', border: 'border-purple-200' },
  crewGroup: { label: 'Crew Group', accent: 'bg-slate-500', border: 'border-slate-200' },
  stickyNote: { label: 'Note', accent: 'bg-amber-400', border: 'border-amber-200' },
  ifElse: { label: 'IF / ELSE', accent: 'bg-amber-500', border: 'border-amber-200' },
  switch: { label: 'Switch', accent: 'bg-cyan-500', border: 'border-cyan-200' },
  merge: { label: 'Merge', accent: 'bg-indigo-500', border: 'border-indigo-200' },
  filter: { label: 'Filter', accent: 'bg-orange-500', border: 'border-orange-200' },
  gate: { label: 'Gate', accent: 'bg-teal-500', border: 'border-teal-200' },
  loop: { label: 'Loop', accent: 'bg-pink-500', border: 'border-pink-200' },
  crewComponent: { label: 'Crew', accent: 'bg-primary', border: 'border-primary/30' },
}

export default function PropertyPanel() {
  const selectedNodeId = useStudioStore((s) => s.selectedNodeId)
  const selectedNode = useStudioStore(
    useShallow((state) => {
      if (!state.selectedNodeId) return null
      const n = state.nodes.find((node) => node.id === state.selectedNodeId)
      if (!n) return null
      return { id: n.id, type: n.type, data: n.data }
    }),
  )
  const updateNodeData = useStudioStore((s) => s.updateNodeData)
  const setSelectedNode = useStudioStore((s) => s.setSelectedNode)
  const removeNode = useStudioStore((s) => s.removeNode)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const onChange = useCallback(
    (field: string, value: unknown) => {
      if (!selectedNodeId) return
      updateNodeData(selectedNodeId, { [field]: value })
    },
    [selectedNodeId, updateNodeData],
  )

  // Close panel on Escape key (skip if delete confirm dialog is open — let Radix handle it)
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && selectedNodeId && !showDeleteConfirm) {
        setSelectedNode(null)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [selectedNodeId, setSelectedNode, showDeleteConfirm])

  const nodeType = selectedNode?.type ?? 'agent'
  const data = selectedNode?.data
  const meta = TYPE_META[nodeType] ?? {
    label: nodeType,
    accent: 'bg-slate-500',
    border: 'border-slate-200',
  }
  const yamlContent = useMemo(
    () => (selectedNode ? nodeToYaml(nodeType, selectedNode.id, data!) : ''),
    [selectedNode, nodeType, data],
  )

  if (!selectedNode || !data) {
    return (
      <aside
        aria-label="Node properties"
        className="hidden w-[300px] shrink-0 flex-col items-center justify-center border-l bg-card p-6 text-center sm:flex"
      >
        <p className="text-sm font-medium text-muted-foreground">No node selected</p>
        <p className="mt-1 text-xs text-muted-foreground/70">
          Click a node on the canvas to edit its properties
        </p>
      </aside>
    )
  }

  return (
    <aside
      aria-label="Node properties"
      className="absolute right-0 top-0 z-20 flex h-full w-[300px] shrink-0 flex-col overflow-hidden border-l bg-card shadow-lg sm:static sm:z-auto sm:shadow-none"
    >
      {/* Header */}
      <div
        className={`flex items-center justify-between border-b px-4 py-3 ${meta.border} bg-card`}
      >
        <div className="flex items-center gap-2">
          <div className={`h-2 w-2 rounded-full ${meta.accent}`} />
          <span className="text-sm font-semibold text-foreground">{meta.label} Properties</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title={`Delete ${meta.label.toLowerCase()}`}
            aria-label={`Delete ${meta.label.toLowerCase()}: ${(data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? selectedNode.id}`}
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={() => setSelectedNode(null)}
            className="flex h-11 w-11 items-center justify-center rounded text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            title="Close"
            aria-label="Close panel"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs.Root defaultValue="properties" className="flex min-h-0 flex-1 flex-col">
        <Tabs.List aria-label="View mode" className="flex shrink-0 border-b bg-muted/30">
          {['properties', 'yaml'].map((tab) => (
            <Tabs.Trigger
              key={tab}
              value={tab}
              className="flex-1 px-3 py-2.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:bg-background data-[state=active]:text-foreground"
            >
              {tab === 'yaml' ? 'YAML' : 'Properties'}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {/* Properties tab */}
        <Tabs.Content value="properties" className="min-h-0 flex-1 overflow-y-auto p-4">
          {nodeType === 'agent' ? (
            <AgentForm data={data} onChange={onChange} />
          ) : nodeType === 'task' ? (
            <TaskForm data={data} onChange={onChange} />
          ) : nodeType === 'tool' ? (
            <ToolForm data={data} onChange={onChange} />
          ) : nodeType === 'flowStep' ? (
            <FlowStepForm data={data} onChange={onChange} />
          ) : nodeType === 'pii' ? (
            <PIIForm data={data} onChange={onChange} />
          ) : nodeType === 'condition' ? (
            <ConditionForm data={data} onChange={onChange} />
          ) : nodeType === 'router' ? (
            <RouterForm data={data} onChange={onChange} />
          ) : nodeType === 'parallel' ? (
            <ParallelForm data={data} onChange={onChange} />
          ) : nodeType === 'crewGroup' ? (
            <CrewGroupForm data={data} onChange={onChange} />
          ) : nodeType === 'stickyNote' ? (
            <StickyNoteForm data={data} onChange={onChange} />
          ) : nodeType === 'ifElse' ? (
            <IfElseForm data={data} onChange={onChange} />
          ) : nodeType === 'switch' ? (
            <SwitchForm data={data} onChange={onChange} />
          ) : nodeType === 'merge' ? (
            <MergeForm data={data} onChange={onChange} />
          ) : nodeType === 'filter' ? (
            <FilterForm data={data} onChange={onChange} />
          ) : nodeType === 'gate' ? (
            <GateForm data={data} onChange={onChange} />
          ) : nodeType === 'loop' ? (
            <LoopForm data={data} onChange={onChange} />
          ) : nodeType === 'crewComponent' ? (
            <CrewComponentForm data={data} onChange={onChange} />
          ) : (
            <p className="text-xs text-muted-foreground">No properties for this node type.</p>
          )}
        </Tabs.Content>

        {/* YAML tab */}
        <Tabs.Content value="yaml" className="flex min-h-0 flex-1 flex-col">
          <div className="border-b p-3">
            <p className="text-2xs text-muted-foreground">Read-only preview of the resource YAML</p>
          </div>
          <div className="min-h-0 flex-1 overflow-auto" role="region" aria-label="YAML preview">
            <CodeBlock code={yamlContent} language="yaml" className="rounded-none border-0" />
          </div>
        </Tabs.Content>
      </Tabs.Root>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Node"
        description={`Delete the ${meta.label.toLowerCase()} "${(data['role'] as string | undefined) ?? (data['name'] as string | undefined) ?? selectedNode.id}" and all its connections? You can undo with ${modKey}+Z.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => {
          removeNode(selectedNode.id)
          setShowDeleteConfirm(false)
          requestAnimationFrame(() => {
            document.querySelector<HTMLElement>('[data-tour="canvas"]')?.focus()
          })
        }}
      />
    </aside>
  )
}
