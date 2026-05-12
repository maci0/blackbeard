import { useCallback, useEffect, useState, createContext, useContext, type ChangeEvent } from 'react'
import * as Tabs from '@radix-ui/react-tabs'
import Editor from '@monaco-editor/react'
import { X, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useStudioStore } from '@/stores/studioStore'
import { useResourceStore } from '@/stores/resourceStore'
import { nodeToYaml } from '@/lib/utils'
import { ConfirmDialog } from '@/components/ui/ConfirmDialog'

/* ------------------------------------------------------------------ */
/* Shared form primitives                                               */
/* ------------------------------------------------------------------ */

/** Context providing a generated field id from the enclosing FieldGroup */
const FieldIdContext = createContext<string>('')

function Label({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) {
  return (
    <label
      htmlFor={htmlFor}
      className="block text-[10px] font-semibold text-muted-foreground uppercase tracking-wider mb-1"
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
    'w-full text-[12px] text-foreground bg-background border border-border rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring placeholder:text-muted-foreground/50 resize-none transition-colors'

  if (multiline) {
    return (
      <textarea
        id={fieldId || undefined}
        className={cls}
        rows={3}
        value={value}
        placeholder={placeholder}
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
      className="w-full text-[12px] text-foreground bg-background border border-border rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring transition-colors"
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
    <label className="flex items-center gap-2 cursor-pointer">
      <input
        type="checkbox"
        className="rounded border-border w-3.5 h-3.5 accent-primary"
        checked={checked}
        onChange={(e: ChangeEvent<HTMLInputElement>) => onChange(e.target.checked)}
      />
      <span className="text-[12px] text-foreground">{label}</span>
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

/* ------------------------------------------------------------------ */
/* Per-type property forms                                             */
/* ------------------------------------------------------------------ */

function AgentForm({
  data,
  onChange,
}: {
  data: Record<string, unknown>
  onChange: (field: string, value: unknown) => void
}) {
  const str = (key: string) => (data[key] as string | undefined) ?? ''
  const bool = (key: string) => (data[key] as boolean | undefined) ?? false

  const llmConnections = useResourceStore((state) => state.resources['llm-connections'] ?? [])
  const fetchResources = useResourceStore((state) => state.fetchResources)

  useEffect(() => {
    fetchResources('llm-connections')
  }, [fetchResources])

  return (
    <div className="space-y-3">
      <FieldGroup label="Role">
        <TextInput value={str('role')} onChange={(v) => onChange('role', v)} placeholder="Senior Researcher" />
      </FieldGroup>
      <FieldGroup label="Goal">
        <TextInput
          value={str('goal')}
          onChange={(v) => onChange('goal', v)}
          placeholder="What should this agent achieve?"
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Backstory">
        <TextInput
          value={str('backstory')}
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
            value={str('llm')}
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
        checked={bool('verbose')}
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
  const str = (key: string) => (data[key] as string | undefined) ?? ''

  const agentNodes = useStudioStore((state) => state.nodes.filter((n) => n.type === 'agent'))

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput value={str('name')} onChange={(v) => onChange('name', v)} placeholder="research_topic" />
      </FieldGroup>
      <FieldGroup label="Description">
        <TextInput
          value={str('description')}
          onChange={(v) => onChange('description', v)}
          placeholder="Describe what this task does..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Expected Output">
        <TextInput
          value={str('expected_output')}
          onChange={(v) => onChange('expected_output', v)}
          placeholder="A detailed report on..."
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Agent">
        <SelectInput
          value={str('agent')}
          onChange={(v) => onChange('agent', v)}
          options={[
            { value: '', label: 'Select agent...' },
            ...agentNodes.map((node) => {
              const nodeData = node.data as Record<string, unknown>
              const role = (nodeData.role as string | undefined) ?? ''
              const kebabName =
                (nodeData.name as string | undefined) ||
                role.toLowerCase().replace(/\s+/g, '-').replace(/[^a-z0-9-]/g, '')
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
  const str = (key: string) => (data[key] as string | undefined) ?? ''

  return (
    <div className="space-y-3">
      <FieldGroup label="Name">
        <TextInput value={str('name')} onChange={(v) => onChange('name', v)} placeholder="web_search_tool" />
      </FieldGroup>
      <FieldGroup label="Type">
        <SelectInput
          value={str('type') || 'python'}
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
          value={str('class_path')}
          onChange={(v) => onChange('class_path', v)}
          placeholder="my_module.MyTool"
        />
      </FieldGroup>
      <FieldGroup label="Description">
        <TextInput
          value={str('description')}
          onChange={(v) => onChange('description', v)}
          placeholder="What does this tool do?"
          multiline
        />
      </FieldGroup>
      <FieldGroup label="Sandbox">
        <SelectInput
          value={str('sandbox') || 'none'}
          onChange={(v) => onChange('sandbox', v)}
          options={[
            { label: 'No sandbox', value: 'none' },
            { label: 'Restricted', value: 'restricted' },
            { label: 'Isolated', value: 'isolated' },
          ]}
        />
      </FieldGroup>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Panel header accent colours per type                                */
/* ------------------------------------------------------------------ */

const TYPE_META: Record<string, { label: string; accent: string; border: string }> = {
  agent: { label: 'Agent', accent: 'bg-violet-500', border: 'border-violet-200' },
  task: { label: 'Task', accent: 'bg-blue-500', border: 'border-blue-200' },
  tool: { label: 'Tool', accent: 'bg-emerald-500', border: 'border-emerald-200' },
}

/* ------------------------------------------------------------------ */
/* Main panel                                                           */
/* ------------------------------------------------------------------ */

export default function PropertyPanel() {
  const { nodes, selectedNodeId, updateNodeData, setSelectedNode, removeNode } = useStudioStore()
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)

  const selectedNode = nodes.find((n) => n.id === selectedNodeId)

  const onChange = useCallback(
    (field: string, value: unknown) => {
      if (!selectedNodeId) return
      updateNodeData(selectedNodeId, { [field]: value })
    },
    [selectedNodeId, updateNodeData],
  )

  if (!selectedNode) return null

  const nodeType = selectedNode.type ?? 'agent'
  const data = selectedNode.data as Record<string, unknown>
  const meta = TYPE_META[nodeType] ?? { label: nodeType, accent: 'bg-slate-500', border: 'border-slate-200' }
  const yamlContent = nodeToYaml(nodeType, selectedNode.id, data)

  return (
    <aside className="w-[300px] shrink-0 border-l bg-card flex flex-col overflow-hidden">
      {/* Header */}
      <div className={`flex items-center justify-between px-4 py-3 border-b ${meta.border} bg-card`}>
        <div className="flex items-center gap-2">
          <div className={`w-2 h-2 rounded-full ${meta.accent}`} />
          <span className="text-sm font-semibold text-foreground">{meta.label} Properties</span>
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={() => setShowDeleteConfirm(true)}
            className="p-1 rounded text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            title="Delete node"
            aria-label="Delete node"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setSelectedNode(null)}
            className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none"
            title="Close"
            aria-label="Close panel"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <Tabs.Root defaultValue="properties" className="flex flex-col flex-1 min-h-0">
        <Tabs.List className="flex border-b bg-muted/30 shrink-0">
          {['properties', 'yaml'].map((tab) => (
            <Tabs.Trigger
              key={tab}
              value={tab}
              className="flex-1 text-[11px] font-semibold uppercase tracking-wider px-3 py-2.5 text-muted-foreground data-[state=active]:text-foreground data-[state=active]:bg-background data-[state=active]:border-b-2 data-[state=active]:border-primary transition-colors"
            >
              {tab}
            </Tabs.Trigger>
          ))}
        </Tabs.List>

        {/* Properties tab */}
        <Tabs.Content value="properties" className="flex-1 overflow-y-auto p-4 min-h-0">
          {nodeType === 'agent' && <AgentForm data={data} onChange={onChange} />}
          {nodeType === 'task' && <TaskForm data={data} onChange={onChange} />}
          {nodeType === 'tool' && <ToolForm data={data} onChange={onChange} />}
          {nodeType !== 'agent' && nodeType !== 'task' && nodeType !== 'tool' && (
            <p className="text-xs text-muted-foreground">No properties for this node type.</p>
          )}
        </Tabs.Content>

        {/* YAML tab */}
        <Tabs.Content value="yaml" className="flex flex-col flex-1 min-h-0">
          <div className="p-3 border-b">
            <p className="text-[10px] text-muted-foreground">
              Read-only preview of the resource YAML
            </p>
          </div>
          <div className="flex-1 min-h-0">
            <Editor
              height="100%"
              language="yaml"
              value={yamlContent}
              theme="vs"
              options={{
                readOnly: true,
                minimap: { enabled: false },
                scrollBeyondLastLine: false,
                fontSize: 11,
                lineNumbers: 'off',
                folding: false,
                wordWrap: 'on',
                padding: { top: 12, bottom: 12 },
                overviewRulerLanes: 0,
                hideCursorInOverviewRuler: true,
                scrollbar: { verticalScrollbarSize: 4 },
              }}
            />
          </div>
        </Tabs.Content>
      </Tabs.Root>

      <ConfirmDialog
        open={showDeleteConfirm}
        onOpenChange={setShowDeleteConfirm}
        title="Delete Node"
        description={`Delete this ${meta.label.toLowerCase()} node and all its connections? You can undo with Cmd+Z.`}
        confirmLabel="Delete"
        confirmVariant="destructive"
        onConfirm={() => {
          removeNode(selectedNode.id)
          setShowDeleteConfirm(false)
        }}
      />
    </aside>
  )
}
