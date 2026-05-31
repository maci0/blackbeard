# PRD 02 — Visual Graph Editor (Studio)

## 1. Purpose

Provide a browser-based drag-and-drop canvas where users compose agents, tasks, and flows visually. The graph IS the source of truth — every node and edge maps 1:1 to the YAML resource model (PRD 01). Changes on canvas instantly update the underlying YAML; edits to YAML instantly update the canvas.

### 1.1 MVP Scope

**Implemented:** Canvas with Agent/Task/Tool nodes, edges for context and tool assignment, property panel with spec fields, YAML editor with bidirectional sync (Monaco), save to API, Run/Train/Test mode selector, FlowStep nodes, CrewGroup compound nodes (bounding box), ELK.js auto-layout, undo/redo (30 snapshots), execution view with status badges. Assistant (prompt-to-crew via LiteLLM, Sparkles button + dialog, `api/copilot.py` + `engine/copilot.py`). Live collaboration (WebSocket rooms, participant count, node/edge sync, auto-reconnect). Cursor presence (colored cursors + names for collaborating users).

**Implemented additionally:** Command palette (Cmd+K) for global search across resources. Resource clone/duplicate. YAML file import on Resources page. Resource creation dialog on Resources page. Execution retry button. HITL response panel (frontend polls for `hitl_request` events, submits responses via API). Studio state persists to `localStorage`. Execution filtering (status, crew, type) with sortable columns. Sticky notes on canvas (4 color variants, editable inline text). Execution data overlay on nodes (green/red borders for success/failure, output preview on hover, "Clear Results" button). Per-node testing ("Test Agent" / "Test Task" buttons in PropertyPanel, uses first available LLMConnection). Condition, Router, and Parallel node types with dedicated property forms. Expression editor with syntax validation and variable autocomplete for condition/router expressions. Crew Settings dialog (error workflow: run error crew / retry N times / ignore). Canvas JSON export (toolbar "Export" + "Copy as JSON" buttons). Execution timeline / Gantt chart (horizontal bars per task, status-colored, time scale axis). Grouped/collapsible execution logs (group by task with expand/collapse, similar to GitHub Actions log groups).

**Partial:** Training tab -- Run/Train/Test modes available in RunDialog; dedicated training panel with feedback workflow (section 7.1) deferred.

**Implemented (post-MVP):** Canvas export PNG/SVG via html-to-image in the Export dropdown.

**Deferred to post-MVP:** Export ZIP/React, drag reparenting.

---

## 1.2 Component Library & Logic Blocks (Post-MVP)

Inspired by digital logic simulators (Logisim, Digital), the Studio gains a component library system and logic blocks for reusable, composable crew design.

### Crew-as-Component (Subcircuit Pattern)

Any saved Crew can be used as a single node inside another Crew or Flow — like a subcircuit in Logisim. The crew-component node shows the crew's `spec.inputs` as labeled input ports on the left edge and a single output port on the right.

- **Save as component**: Right-click a CrewGroup → "Save as Component". The crew is saved to the API and appears in the palette under "My Components".
- **Drag to canvas**: Drag a crew-component from the palette. It renders as a compact node with the crew name, agent/task count badge, and input/output ports.
- **Drill-in editing**: Double-click a crew-component node to navigate into its internal canvas. A breadcrumb bar shows the navigation depth (e.g., `Pipeline > Research Stage`). Click breadcrumb to navigate back up.
- **Data flow**: The output of one crew-component feeds into the next crew-component's inputs via edges. At execution time, the engine chains crew kickoffs sequentially, passing outputs as inputs.

### Typed Ports

Nodes gain explicit named input/output handles (ports) on their edges, replacing the current untyped connection model:

- **Task nodes**: Left port = `context` (input from upstream tasks/agents), right port = `output` (task result text).
- **Agent nodes**: Bottom port = `tasks` (connects to assigned tasks), top port = `tools` (connects to tool nodes).
- **Crew-component nodes**: Left ports = one per `spec.inputs[].name`, right port = `output`.
- **Logic block nodes**: Left ports = input values, right ports = output per branch.
- **Port labels**: Visible on hover (300ms delay) or always visible at zoom > 100%.
- **Type validation**: Ports carry a type hint (`text`, `json`, `boolean`, `number`). Invalid connections (e.g., boolean port → text port) show a red indicator.

### Logic Blocks for Decision Making

New node types for branching and control flow, inspired by digital logic gates:

| Node | Inputs | Outputs | Behavior |
|------|--------|---------|----------|
| **IF/ELSE** | `condition` (expression), `input` (data) | `true` branch, `false` branch | Evaluates condition expression against input data. Routes to true or false output port. |
| **Switch** | `value` (data), `cases` (configured values) | One output port per case + `default` | Matches value against case labels. Routes to matching output port. Like a Router but visual with explicit output ports per case. |
| **Merge** | Multiple inputs | Single output | Waits for all inputs to arrive, then merges them into a single output dict. For parallel-to-sequential convergence. |
| **Filter** | `input` (list/array), `condition` (expression) | `passed`, `rejected` | Filters input items by condition. Items matching go to `passed` port, others to `rejected`. |
| **Loop** | `items` (list), `body` (connected subgraph) | `results` (list) | Iterates over items, executing the connected subgraph for each. Collects results. |
| **Gate** | `input`, `control` (boolean) | `output` | Passes input through only when control is true. Otherwise blocks (returns null). Like a digital AND gate for data flow. |

Each logic block:
- Has a distinct visual shape (diamond for IF/ELSE, hexagon for Switch, circle for Merge)
- Shows the condition/expression inline on the node
- Supports the expression editor with variable autocomplete
- Can be tested individually via "Test Node" in PropertyPanel

### Saved Component Library

The palette gains a "My Components" section:

- **Save**: Right-click any node group → "Save as Component" → name + description dialog
- **Categories**: Components are tagged (e.g., "Research", "Content", "Data") for filtering
- **Versioning**: Each save creates a new version. Old versions remain usable.
- **Import/Export**: Components can be exported as YAML and imported into other Blackbeard instances via the Marketplace.
- **Parameters**: Components define `parameters` that are configurable when dragged onto the canvas (like component properties in Logisim).

### Execution Wire Values

During and after execution, edges (wires) display the data that flowed through them:

- **Live**: Edges animate with a flowing dot pattern during execution (CSS animation on the SVG path).
- **Completed**: Click any edge to see a tooltip with the data payload (truncated to 500 chars, "Show full" button for expansion).
- **Token count**: Edge tooltip shows token count for the upstream task's LLM calls.
- **Error propagation**: If an upstream task fails, downstream edges turn red with an error icon.

---

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

### 3.6 Condition Node

**Status: Implemented (beyond MVP).**

- **Display**: Diamond shape with condition label, true/false output port labels.
- **Ports**: Single input, two outputs (true branch, false branch).
- **Property form**: Expression editor with syntax validation and variable autocomplete. Supports referencing prior task outputs and flow state variables.
- **Edge rules**: True output connects to the step executed when condition is met; false output to the alternative.

### 3.7 Router Node

**Status: Implemented (beyond MVP).**

- **Display**: Diamond shape with labelled output ports for each route.
- **Ports**: Single input, N outputs (one per route label).
- **Property form**: Route definitions with label and condition pairs. Expression editor with variable autocomplete for each route condition.
- **Edge rules**: Each output port connects to the downstream step for that route.

### 3.8 Parallel Node

**Status: Implemented (beyond MVP).**

- **Display**: Horizontal bar with fork/join indicators, containing child step references.
- **Ports**: Single input (fork point), single output (join point after all parallel branches complete).
- **Property form**: List of parallel branch step references with add/remove controls.
- **Edge rules**: Downstream steps wait for all parallel branches to complete before proceeding.

### 3.9 Sticky Note

**Status: Implemented (beyond MVP).**

- **Display**: Colored rectangle (4 color variants: yellow, blue, green, pink) with editable inline text.
- **Not connectable**: Sticky notes have no ports and cannot participate in edges.
- **Purpose**: Annotation-only -- allows users to leave notes, reminders, or documentation on the canvas.
- **Inline editing**: Double-click to edit text directly on the canvas.

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

### 5.1 Expression Editor (Implemented)

Condition and Router nodes include a dedicated **expression editor** widget:

- **Syntax validation**: Real-time syntax checking with inline error markers.
- **Variable autocomplete**: Suggests available variables from prior task outputs, flow state, and execution inputs. Triggered by typing `{{` or pressing Ctrl+Space.
- **Preview**: Shows the expression's evaluated type and a preview of what the expression would resolve to given sample data.

### 5.2 Per-Node Testing (Implemented)

The PropertyPanel includes **"Test Agent"** and **"Test Task"** buttons for individual node testing:

- **Test Agent**: Runs the selected agent against a sample task using the first available LLMConnection. Results displayed inline in the PropertyPanel.
- **Test Task**: Runs the selected task with its assigned agent. Results include output preview, token usage, and duration.
- Uses the first available model from configured LLMConnections -- no manual model selection required.

### 5.3 Crew Settings Dialog (Implemented)

Accessible via the crew group node's context menu or the toolbar, the Crew Settings dialog configures crew-level behavior:

- **Error workflow**: Three options -- run a designated error crew, retry N times with backoff, or ignore errors and continue.
- **Settings are persisted** to the Crew resource's `spec` on save.

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
| Undo/Redo | Ctrl+Z / Ctrl+Shift+Z | Full undo stack (30 snapshots) |
| Copy/Paste | Ctrl+C / Ctrl+V | Deep-copies selected nodes with new names |
| Search | Ctrl+K | Fuzzy search all nodes on canvas |
| Validate | Toolbar button | Runs validation (PRD 01, section 6) and highlights errors on nodes |

> **Note:** Validate is available via the toolbar button. The keyboard shortcut was removed to avoid conflict with browser paste-without-formatting (`Ctrl+Shift+V`).

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
- **Execution timeline / Gantt chart (Implemented)**: A timeline bar at the bottom shows task start/end with horizontal bars per task, status-colored (green=completed, red=failed, blue=running, gray=pending), with a time scale axis. Hover shows duration, tokens, and cost.
- **Execution data overlay (Implemented)**: Nodes display green borders on success, red borders on failure, with output preview on hover. A "Clear Results" button resets the overlay.
- Errors highlight the failed node in red with the error message inline.
- **Loading state**: While waiting for execution to start, all nodes show a pulsing gray border. A "Connecting to execution..." overlay appears if SSE connection takes >3s.
- **Error recovery**: If the SSE stream disconnects, the UI polls `GET /executions/{id}` every 5s as fallback. A "Reconnecting..." banner shows at the top of the canvas. When SSE reconnects, polling stops.
- **Stale execution**: If an execution hasn't emitted events for >5 minutes, a "Execution may be stalled" warning appears on the current task node. The 5-minute threshold is configurable via execution metadata. For long-running LLM calls (reasoning models, large context), the threshold is automatically extended to `agent.max_execution_time * 1.5` if defined.

**Grouped/collapsible execution logs (Implemented)**: Execution events in the log panel are grouped by task, with expand/collapse controls similar to GitHub Actions log groups. Each group header shows the task name, status badge, duration, and token count. Expanding a group reveals individual events (LLM calls, tool calls, policy events) within that task.

**Node-to-execution mapping**: Canvas nodes use the convention `{kind}-{name}` as their React Flow node ID (e.g., `task-research-ai`, `agent-researcher`). Execution SSE events carry `task_name` and `agent_name` fields. The UI maps events to nodes by constructing the node ID from the event's resource name. If a node ID doesn't match any canvas node (e.g., a dynamically-created subtask in hierarchical mode), the event is displayed in a "Unmapped Events" panel below the canvas. This convention must match the SSE event payload format defined in PRD 05. Execution SSE events carry `event_type`, `task_name`, and `agent_name` fields that map to canvas nodes via `{kind}-{name}` node IDs.

## 7.1 Agent Training & Testing UI

When viewing an Agent resource detail page (navigated from Studio or Resources list), a **Training** tab provides an interactive training workflow powered by CrewAI's built-in training system (see PRD 05, §11.5).

### Training Panel Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Agent: Researcher                                    [Train ▼] │
├─────────────────────────────────────────────────────────────────┤
│  Tabs: [Overview] [Spec] [YAML] [Training] [History]            │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  Start Training Session                                  │    │
│  │                                                         │    │
│  │  Crew:  [research-crew          ▼]  (crews using agent) │    │
│  │  Iterations: [3     ]                                    │    │
│  │  Inputs (JSON): {"topic": "AI safety"}                  │    │
│  │                                                         │    │
│  │  [Start Training]                                       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ── Active Session: Iteration 2/3 ──                           │
│                                                                 │
│  Agent Output:                                                  │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ 1. AI safety research has identified alignment as...     │    │
│  │ 2. Interpretability techniques like mechanistic...       │    │
│  │ 3. Governance frameworks are being developed by...       │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  Your Feedback:                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │ Good facts but too verbose. Keep each bullet to one      │    │
│  │ sentence max. Focus more on technical approaches.        │    │
│  └─────────────────────────────────────────────────────────┘    │
│  [Submit Feedback & Continue]                                   │
│                                                                 │
│  ── Training History ──────────────────────────────────────     │
│                                                                 │
│  │ Session    │ Crew          │ Iterations │ Score │ Date       │
│  │ train-001  │ research-crew │ 3/3 ✓      │ 8.5   │ May 14    │
│  │ train-002  │ analysis-crew │ 5/5 ✓      │ 7.2   │ May 13    │
│                                                                 │
│  ── Test Results ─────────────────────────────────────────     │
│  [Run Test]  Iterations: [5]  Eval Model: [gpt-4o ▼]          │
│                                                                 │
│  Last test: avg 8.2 | research-topic: 8.5 | write-report: 7.9 │
│  ┌────────────────────────────────────────┐                     │
│  │  Score  ██████████████░░ 8.2/10        │                     │
│  │  █ █ █ █ █  (per-iteration scores)     │                     │
│  └────────────────────────────────────────┘                     │
└─────────────────────────────────────────────────────────────────┘
```

### Entry Points

| Location | Action | Behavior |
|----------|--------|----------|
| **Resource Detail** (`/resources/agents/{name}`) | Training tab | Full training panel |
| **Studio** → Agent node → Property Panel | "Train" button | Navigates to `/resources/agents/{name}?tab=training` |
| **Crew Detail** (`/resources/crews/{name}`) | "Train Crew" action button | Navigates to training UI pre-selecting this crew |

### Interaction Flow

1. **Select crew**: Dropdown shows all crews that reference this agent (queried via `ref:agents/{name}` lookup).
2. **Configure**: Set iteration count (1-20) and provide sample inputs as JSON.
3. **Start**: `POST /api/v1/crews/{name}/train` — session created, first iteration runs.
4. **Review**: After each iteration, the UI displays agent outputs. Human types feedback in a text area.
5. **Submit**: `POST /api/v1/training-sessions/{id}/feedback` — next iteration starts.
6. **Complete**: After all iterations, the summary shows per-agent quality scores and consolidated suggestions.
7. **Test**: Optionally run `POST /api/v1/crews/{name}/test` to benchmark the trained agent with an eval model.

### Acceptance Criteria (UI)

- Training tab appears on Agent resource detail pages.
- Crew dropdown only shows crews that use this agent.
- Feedback text area supports multi-line input and Cmd+Enter to submit.
- Progress indicator shows current iteration / total.
- Training history table shows past sessions with clickable rows for detail.
- Test results display per-task scores with a simple bar chart.
- "Train" button in Studio Property Panel navigates correctly.

## 8. Assistant

An optional chat sidebar (left panel) for prompt-based creation:

- **"Create a crew that…"** → AI generates agent, task, and tool nodes on canvas.
- **"Add a guardrail to task X that…"** → AI adds guardrail spec.
- **"Connect agent A to task B"** → AI creates the edge.
- **"Explain this flow"** → AI describes the current canvas state in natural language.

Assistant always generates YAML that passes validation. User can accept/reject each change.

*Assistant is implemented. Prompt-to-crew generation via LiteLLM with Sparkles button + dialog (`api/copilot.py`, `engine/copilot.py`).*

## 9. Import / Export

| Action | Format |
|--------|--------|
| **Import** | Upload a folder of YAML files → parsed into canvas nodes |
| **Export YAML** | Download all resources as a directory of YAML files |
| **Export JSON (Implemented)** | Toolbar "Export" button downloads canvas state as JSON; "Copy as JSON" copies to clipboard |
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
| Assistant | Streaming LLM via backend API | Uses whatever LLM the user has configured |

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
- **Live collaboration**: Implemented via WebSocket rooms with Valkey pub/sub, participant count, node/edge sync, auto-reconnect, and cursor presence (colored cursors + names).

## 12. Canvas Persistence

- Each Crew or Flow resource has an associated **canvas layout** stored **frontend-only** in the Zustand store and persisted to `localStorage` (no server-side `canvas_layouts` database table exists). Layout data includes React Flow node positions, viewport offset, and zoom level.
- Layout is saved automatically to `localStorage` on every canvas change (debounced) and on explicit "Save" (which persists resource specs to the API but keeps layout data local).
- A canvas displays **one Crew or Flow** at a time. Multi-crew canvases are deferred to post-MVP.
- If no layout exists (e.g., resource created via CLI), the canvas auto-layouts using ELK.js on first open.
- **Concurrent editing**: Live collaboration is implemented via WebSocket rooms with Valkey pub/sub. Multiple users can edit the same canvas simultaneously with node/edge sync, cursor presence, and auto-reconnect. Canvas layout conflicts use last-write-wins -- the canvas layout is non-critical data, and losing a layout just triggers auto-layout on next open.

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
8. Undo/Redo works across all operations including node creation, deletion, edge changes, and property edits (30-snapshot ring buffer).

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
