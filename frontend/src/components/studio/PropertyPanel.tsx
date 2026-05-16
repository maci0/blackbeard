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
import { X, Trash2 } from 'lucide-react'
import { CodeBlock } from '@/components/ui/CodeBlock'
import { Link } from 'react-router-dom'
import { useStudioStore } from '@/stores/studioStore'
import { useResourceStore, type Resource } from '@/stores/resourceStore'
import { modKey } from '@/lib/platform'
import { nodeToYaml } from './nodeYaml'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'

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
    <label className="flex cursor-pointer items-center gap-2">
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
          <SelectInput
            value={str(data, 'llm')}
            onChange={(v) => onChange('llm', v)}
            options={[
              { value: '', label: 'Select LLM connection...' },
              ...llmConnections.map((conn) => {
                const model = (conn.spec.model as string | undefined) ?? ''
                return {
                  value: `ref:llm-connections/${conn.metadata.name}`,
                  label: model ? `${conn.metadata.name} (${model})` : conn.metadata.name,
                }
              }),
            ]}
          />
        )}
      </FieldGroup>
      <CheckboxInput
        label="Verbose"
        checked={bool(data, 'verbose')}
        onChange={(v) => onChange('verbose', v)}
      />
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
          options={[
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
          ]}
        />
      </FieldGroup>
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

const TYPE_META: Record<string, { label: string; accent: string; border: string }> = {
  agent: { label: 'Agent', accent: 'bg-violet-500', border: 'border-violet-200' },
  task: { label: 'Task', accent: 'bg-blue-500', border: 'border-blue-200' },
  tool: { label: 'Tool', accent: 'bg-emerald-500', border: 'border-emerald-200' },
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
        description={`Delete this ${meta.label.toLowerCase()} node and all its connections? You can undo with ${modKey}+Z.`}
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
