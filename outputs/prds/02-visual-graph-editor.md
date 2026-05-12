# PRD 02 — Visual Graph Editor (Studio)

## 1. Purpose

Provide a browser-based drag-and-drop canvas where users compose agents, tasks, and flows visually. The graph IS the source of truth — every node and edge maps 1:1 to the YAML resource model (PRD 01). Changes on canvas instantly update the underlying YAML; edits to YAML instantly update the canvas.

## 2. Core Concepts

| Concept | Definition |
|---------|------------|
| **Canvas** | Infinite 2D space with pan, zoom, minimap |
| **Node** | A visual block representing an Agent, Task, Crew step, Flow step, or Tool |
| **Edge** | A directed arrow representing data flow, dependency, or delegation |
| **Panel** | A side panel for editing the selected node's properties (YAML fields) |
| **Palette** | A draggable resource palette (agents, tasks, tools) on the left sidebar |

## 3. Node Types

### 3.1 Agent Node

- **Display**: Avatar icon, role name, LLM badge, tool count badge.
- **Ports**: Input (receives task assignment), Output (emits task result).
- **Double-click**: Opens Agent Property Panel.
- **Context menu**: Duplicate, Delete, View YAML, Open in Repository.

### 3.2 Task Node

- **Display**: Task name, assigned agent badge, expected output preview.
- **Ports**: Input (context from prior tasks), Output (result to next tasks / crew output).
- **Edge rules**: An edge FROM Task A TO Task B creates a `context: [ref:tasks/A]` entry on Task B.
- **Guardrail badge**: Small shield icon if guardrails are attached.

### 3.3 Flow Step Node

- **Display**: Step name, type badge (function / crew / agent), trigger label.
- **Ports**: Multiple inputs (for `and_` / `or_` triggers), multiple outputs (for router branches).
- **Router node variant**: Diamond shape with labelled output ports for each route.
- **Human-in-the-loop variant**: Pause icon, shows feedback message preview.

### 3.4 Tool Node

- **Display**: Tool name, type icon (Python / MCP / REST), description snippet.
- **Ports**: Attach to Agent nodes via dashed edge (means "agent can use this tool").
- **Not connectable to Task nodes directly** — tools are assigned through agents.

### 3.5 Crew Node (compound)

- **Display**: A bounding box containing Agent + Task nodes.
- **Collapsible**: Can be collapsed to a single "Crew" block with summary badges.
- **Process mode indicator**: Sequential (numbered chain) or Hierarchical (tree icon).
- **Implementation**: Uses React Flow's `Group` node type. Agent and Task nodes within the crew have `parentId` set to the Crew node's ID. When collapsed, child nodes are hidden and the Crew node renders a summary view with agent count, task count, and process mode.
- **Drag reparenting**: Dragging an Agent or Task node into a Crew bounding box sets its `parentId` to the Crew node and adds a `ref:` entry to the Crew's `spec.agents` or `spec.tasks`. Dragging a node out of a Crew removes the `parentId` and the corresponding `ref:` entry. The Crew's YAML updates immediately on reparent.

## 4. Edge Semantics

| Edge Type | Visual | Semantics |
|-----------|--------|-----------|
| **Data flow** | Solid arrow | Output of source is `context` for target |
| **Tool assignment** | Dashed line | Agent has access to this tool |
| **Delegation** | Dotted arrow with "D" label | Agent may delegate to target agent |
| **Router branch** | Coloured arrow with label | Flow step output routes by label |
| **Listener** | Thin arrow with ear icon | Flow step listens to source step's completion |

## 5. Property Panel

When a node is selected, a right-side panel shows an auto-generated form from the YAML spec schema:

- **Text fields** for `role`, `goal`, `backstory`, `description`.
- **Dropdowns** for `llm`, `process`, `code_execution_mode`, enums.
- **Autocomplete** for `ref:` fields (search available agents, tasks, tools).
- **Tag inputs** for `labels`.
- **Code editor** (Monaco) for `callbacks.*` fields — shows the Python function path with a "Test Import" button.
- **Guardrail editor**: Add function-based (Python path) or LLM-based (free-text string) guardrails.
- **Toggle switches** for booleans (`memory`, `cache`, `verbose`, `reasoning`, etc.).
- **Number inputs** with min/max validation for `max_iter`, `max_rpm`, etc.
- **"View YAML" tab**: Raw YAML editor with live bidirectional sync to the form.

**Custom widgets required**: The following fields cannot be auto-generated from JSON Schema and need dedicated form components:

| Field | Widget | Reason |
|-------|--------|--------|
| `ref:` fields (tools, agents, context) | Autocomplete with resource search | Needs live API query for available resources |
| `callbacks.*` | Text input + "Validate Import" button | Must validate Python dotted path syntax |
| `guardrails` | Mixed list builder | Supports both `ref:` (autocomplete) and free-text (LLM string) entries |
| `llm` / `function_calling_llm` | Dropdown with LLMConnection search | Populated from registered LLMConnection resources |
| `embedder` | Nested form (provider + config) | Structured sub-object, not a flat field |
| `templates.*` | File path picker | Browse project template files |

All other fields (strings, numbers, booleans, enums, tags) use auto-generated inputs from JSON Schema.

## 6. Canvas Operations

| Operation | Trigger | Behaviour |
|-----------|---------|-----------|
| Add node | Drag from Palette | Creates a new resource with default spec |
| Connect | Drag from output port to input port | Creates an edge; updates `context` / `tools` / `trigger` in YAML |
| Disconnect | Click edge → Delete | Removes the relationship from YAML |
| Multi-select | Shift+click or lasso | Group move, group delete, "Create Crew from selection" |
| Group into Crew | Right-click selection → "Wrap in Crew" | Creates a Crew resource containing selected agents + tasks |
| Ungroup Crew | Right-click Crew → "Unwrap" | Dissolves Crew, keeps agents + tasks as standalone |
| Auto-layout | Toolbar button | Dagre/ELK automatic layout |
| Undo/Redo | Ctrl+Z / Ctrl+Shift+Z | Full undo stack (50 levels) |
| Copy/Paste | Ctrl+C / Ctrl+V | Deep-copies selected nodes with new names |
| Search | Ctrl+K | Fuzzy search all nodes on canvas |
| Validate | Toolbar button or Ctrl+Shift+V | Runs validation (PRD 01 §5) and highlights errors on nodes |

## 7. Execution View

A second tab on the canvas switches to **Execution View**:

- Nodes are read-only but show live status: pending → running → completed / failed.
- Edges animate data flow direction during execution.
- Clicking a running/completed node shows:
  - Agent thoughts and reasoning chain.
  - Token usage (prompt / completion / total).
  - Wall-clock time.
  - Raw input/output.
  - Tool calls with arguments and responses.
- A timeline bar at the bottom shows task start/end with Gantt-like visualisation.
- Errors highlight the failed node in red with the error message inline.
- **Loading state**: While waiting for execution to start, all nodes show a pulsing gray border. A "Connecting to execution..." overlay appears if SSE connection takes >3s.
- **Error recovery**: If the SSE stream disconnects, the UI polls `GET /executions/{id}` every 5s as fallback. A "Reconnecting..." banner shows at the top of the canvas. When SSE reconnects, polling stops.
- **Stale execution**: If an execution hasn't emitted events for >5 minutes, a "Execution may be stalled" warning appears on the current task node.

**Node-to-execution mapping**: Canvas nodes use the convention `{kind}-{name}` as their React Flow node ID (e.g., `task-research-ai`, `agent-researcher`). Execution SSE events carry `task_name` and `agent_name` fields. The UI maps events to nodes by constructing the node ID from the event's resource name. If a node ID doesn't match any canvas node (e.g., a dynamically-created subtask in hierarchical mode), the event is displayed in a "Unmapped Events" panel below the canvas. This convention must match the SSE event payload format defined in PRD 05. Execution SSE events carry `event_type`, `task_name`, and `agent_name` fields that map to canvas nodes via `{kind}-{name}` node IDs.

## 8. AI Copilot

An optional chat sidebar (left panel) for prompt-based creation:

- **"Create a crew that…"** → AI generates agent, task, and tool nodes on canvas.
- **"Add a guardrail to task X that…"** → AI adds guardrail spec.
- **"Connect agent A to task B"** → AI creates the edge.
- **"Explain this flow"** → AI describes the current canvas state in natural language.

Copilot always generates YAML that passes validation. User can accept/reject each change.

*AI Copilot is deferred to post-MVP. See MVP Implementation Plan.*

## 9. Import / Export

| Action | Format |
|--------|--------|
| **Import** | Upload a folder of YAML files → parsed into canvas nodes |
| **Export YAML** | Download all resources as a directory of YAML files |
| **Export ZIP** | Download as a deployable project (YAML + pyproject.toml + scaffold) |
| **Export PNG/SVG** | Snapshot of the current canvas |
| **Export React Component** | Generates an embeddable React component for the crew's UI |

## 10. Technology Choices

| Component | Technology | Rationale |
|-----------|------------|-----------|
| Canvas renderer | **React Flow** (xyflow) | Mature, performant, extensive node/edge customisation |
| Layout engine | **ELK.js** | Automatic graph layout (Eclipse Foundation, handles hierarchical and layered layouts) |
| Property forms | **React Hook Form** + JSON Schema | Auto-generated from resource schemas |
| Code editor | **Monaco Editor** | Syntax highlighting for YAML and Python paths |
| State management | **Zustand** | Lightweight, good for undo/redo ring buffer |
| Copilot | Streaming LLM via backend API | Uses whatever LLM the user has configured |

## 11. YAML ↔ Canvas Synchronisation

```
┌──────────┐    parse     ┌───────────┐    render     ┌──────────┐
│  YAML    │ ──────────▶  │  Resource  │ ──────────▶  │  Canvas  │
│  Files   │              │  Graph     │              │  Nodes   │
└──────────┘  ◀──────────  └───────────┘  ◀──────────  └──────────┘
               serialise                   on-change
```

- **Parse**: YAML files → typed resource objects → node/edge graph.
- **On-change**: User edits on canvas → update resource graph → trigger YAML serialisation.
- **Conflict resolution**: If YAML is edited directly in the YAML tab, re-parse and reconcile with canvas state. Last-write-wins with undo history.
- **Live collaboration** (v2): OT/CRDT-based multi-user editing. Not required for v1.

## 12. Canvas Persistence

- Each Crew or Flow resource has an associated **canvas layout** stored server-side as a JSON blob (node positions, zoom level, viewport offset).
- Canvas layout is stored in a `canvas_layouts` table: `(resource_kind VARCHAR(63) NOT NULL, resource_name VARCHAR(255) NOT NULL, namespace VARCHAR(255) NOT NULL DEFAULT 'default', layout JSONB, updated_at TIMESTAMPTZ)`. Unique constraint: `UNIQUE(resource_kind, resource_name, namespace)`.
- Layout is saved automatically on every canvas change (debounced, 500ms) and on explicit "Save".
- A canvas displays **one Crew or Flow** at a time. Multi-crew canvases are deferred to post-MVP.
- If no layout exists (e.g., resource created via CLI), the canvas auto-layouts using ELK.js on first open.
- **Concurrent editing (v1)**: v1 is single-user. If two browser tabs save the same canvas, last-write-wins. The canvas layout is non-critical data -- losing a layout just triggers auto-layout on next open. Multi-user conflict resolution (OT/CRDT) is deferred to v2.

## 13. Accessibility

- All nodes keyboard-navigable (Tab / Arrow keys).
- Screen reader announces node type, name, and connections.
- High-contrast mode for edges and labels.
- Zoom controls accessible via keyboard shortcuts.

**MVP scope:** Accessibility features are aspirational for MVP. The MVP ships with basic keyboard navigation (Tab to cycle nodes, Enter to select, Delete to remove) and ARIA labels on interactive elements. Full accessibility (custom tab order, screen reader announcements for canvas operations, high-contrast mode) is post-MVP.

## 14. Acceptance Criteria

1. User can drag Agent, Task, and Tool nodes onto canvas and connect them with arrows.
2. Connecting two Task nodes creates a `context` reference in the downstream task's YAML.
3. Property Panel shows all spec fields for the selected node kind; changes sync to YAML instantly.
4. "View YAML" tab shows valid YAML that round-trips: edit YAML → canvas updates; edit canvas → YAML updates.
5. Execution View shows live task status, token metrics, and agent reasoning for a running crew.
6. Export YAML produces a valid resource directory that `blackbeard validate` accepts.
7. Canvas supports ≥50 nodes at 60fps during pan/zoom. ≥100 nodes at 30fps minimum. Measured with React Flow's built-in performance profiler.
8. Undo/Redo works across all operations including node creation, deletion, edge changes, and property edits.

## Verification Scenarios

The following scenarios define the minimum acceptance criteria for Studio:

| # | Scenario | Steps | Expected Result |
|---|----------|-------|-----------------|
| 1 | Add node | Drag Agent from Palette → drop on canvas | New Agent node appears; YAML resource created with default spec; API confirms resource exists |
| 2 | Connect edge | Drag from Task A output port → Task B input port | Solid arrow appears; Task B's `context` array updated with `ref:tasks/A` |
| 3 | Edit property | Select Agent node → change `role` in PropertyPanel | Agent node label updates; YAML spec updates; API PUT succeeds |
| 4 | Save crew | Click Save button | All resources persisted via API; canvas layout saved to `canvas_layouts` table |
| 5 | Run crew | Click Run button → wait for completion | Execution created; nodes show status badges (pending → running → completed); execution detail available |
| 6 | YAML sync | Edit YAML in YAML tab → change agent name | Form fields update; canvas node label updates |
| 7 | Undo/redo | Add node → Ctrl+Z → Ctrl+Shift+Z | Node removed on undo, restored on redo |
| 8 | Delete node | Select node → press Delete | Node and its edges removed; resource deleted via API |
