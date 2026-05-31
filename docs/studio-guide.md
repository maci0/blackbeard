# Studio Guide

The Studio is Blackbeard's visual graph editor. You use it to build crews, flows, and agent pipelines by dragging nodes onto a canvas, connecting them with edges, and configuring their properties in a side panel. Everything you build in the Studio saves as standard Blackbeard resources (Agent, Task, Crew, Tool, Flow, Guardrail) through the same API that the CLI and SDK use.

Navigate to the Studio from the sidebar or go directly to `/studio`.

## Interface Layout

The Studio has four zones:

**Palette** (left, 108px wide). A vertical strip of draggable node cards. Each card represents a node type (Agent, Task, Tool, etc.) with a color-coded header. A search input at the top filters the list. Below the built-in node types, a "My Crews" section lists saved crews that you can drag on as reusable Crew Component nodes. On mobile, the palette collapses into a horizontal button bar at the bottom of the screen.

**Canvas** (center). The main work area powered by React Flow. Nodes snap to a 20px grid. The canvas includes a dot-pattern background, zoom/pan controls in the bottom-left corner, a minimap in the bottom-right corner, and a "Fit View" button. When the canvas is empty, an overlay prompts you to drag nodes from the palette or load an example crew.

**Property Panel** (right, 300px wide). Opens when you click a node. Shows a form tailored to the selected node type (Agent fields differ from Task fields, which differ from Condition fields, etc.). Has two tabs: Properties (the editable form) and YAML (a read-only YAML preview of that node). Includes a delete button and a close button. Press Escape to close the panel without deleting.

**Toolbar** (top). A horizontal bar containing the crew name input, Load dropdown, status badge, Undo/Redo buttons, Save, Run, Crew Settings, AI Assistant, Export dropdown, YAML editor toggle, Auto Layout, Collaboration toggle, Presence avatars, and Keyboard Shortcuts.

## Node Types

Each node type has a distinct color and icon. You can drag any of these from the palette onto the canvas or press Enter/Space while focused on a palette card to add it.

### Core Nodes

| Node | Color | Purpose |
|------|-------|---------|
| **Agent** | Violet | An AI agent with a role, goal, backstory, and optional LLM connection |
| **Task** | Blue | A unit of work assigned to an agent, with a description and expected output |
| **Tool** | Green | A tool (Python, WASM, or built-in) that agents can use |
| **Crew Component** | Primary | A reference to a saved crew, used as a reusable building block in flows |

### Flow Nodes

| Node | Color | Purpose |
|------|-------|---------|
| **Flow Step** | Amber | A step in a Flow resource, referencing a crew or function |
| **Condition** | Amber | Evaluates an expression and branches to a true or false target |
| **Router** | Cyan | Routes execution across multiple condition/target pairs |
| **Parallel** | Purple | Runs multiple branches concurrently |

### Logic Nodes

| Node | Color | Purpose |
|------|-------|---------|
| **IF/ELSE** | Amber | Conditional branch with customizable true/false labels |
| **Switch** | Cyan | Multi-way branch based on an expression matching case values |
| **Merge** | Indigo | Joins multiple inputs into one output (wait-all or first-wins) |
| **Filter** | Orange | Splits items by a condition into Passed and Rejected outputs |
| **Gate** | Teal | Blocks or passes data based on a control expression |
| **Loop** | Pink | Iterates over a list expression, with optional parallel execution |

### Utility Nodes

| Node | Color | Purpose |
|------|-------|---------|
| **PII Filter** | Rose | A guardrail that detects and redacts/rejects/warns on PII entities. Includes compliance presets for HIPAA, GDPR, PCI-DSS, and CCPA |
| **Sticky Note** | Yellow/Blue/Green/Pink | A text note on the canvas. Four color options. Not saved as a resource |

### Crew Group Nodes

When you load an existing crew or use the "Load example" feature, the Studio wraps the crew's agents and tasks inside a Crew Group node. This is a container with a label and a gray bounding box that renders behind its children. You can rename the crew group in the Property Panel. Child nodes are visually contained within the group and move with it.

## Building a Crew

### Step 1: Name Your Crew

Type a name into the crew name input at the top-left of the toolbar. Names are normalized to lowercase alphanumeric characters and hyphens (e.g., "My Research Crew" becomes `my-research-crew`). A preview of the normalized name appears if it differs from what you typed.

### Step 2: Add Nodes

Drag nodes from the palette onto the canvas. Each new node gets default placeholder values. For a minimal crew, you need at least one Agent and one Task.

### Step 3: Connect Nodes

Draw edges by clicking a node's output handle and dragging to another node's input handle. The Studio enforces connection rules:

| Source | Valid Targets |
|--------|--------------|
| Agent | Task |
| Task | Task, Agent |
| Tool | Agent, Task |
| Flow Step | Flow Step |

Condition, Router, and Parallel nodes accept connections from any source type.

Sticky Notes cannot be connected to anything.

Connection lines are styled as indigo and edges render with arrow markers at the target end. Tool-to-agent/task edges use a distinct "tool assign" edge style.

### Step 4: Configure Properties

Click any node to open the Property Panel on the right. Fill in the fields specific to that node type.

**Agent** fields: Role, Goal, Backstory, LLM (dropdown of configured LLM connections), Verbose (checkbox).

**Task** fields: Name, Description, Expected Output, Agent (dropdown of agents on the canvas).

**Tool** fields: Name, Type (Python/WASM/Built-in), Class Path, Description, Sandbox (None/WASM).

**Flow Step** fields: Step Name, Type (Crew/Function/Router/Condition), Crew or Function Path (depends on type), Listen To (checkboxes of other flow step names).

**Condition** fields: Name, Condition (expression with syntax validation and autocomplete), True Branch, False Branch (dropdowns of other steps).

**Router** fields: Name, Routes (dynamic list of condition/target pairs, each with an expression editor).

**PII Filter** fields: Compliance Preset (HIPAA/GDPR/PCI-DSS/CCPA/Custom), Entities (13 checkboxes), Action (Redact/Reject/Warn), Backend (Default/Presidio NLP/LiteLLM).

### Step 5: Save

Click the **Save** button or press `Cmd+S` / `Ctrl+S`. The Studio saves each node as its corresponding resource (Agent, Task, Tool, Guardrail) through the API, then synthesizes and saves a Crew resource that references them. If the canvas contains Flow Step nodes, a Flow resource is saved instead of a Crew.

The save button shows a small amber dot when there are unsaved changes. Navigating away from the page with unsaved changes triggers a browser confirmation prompt.

## Loading an Existing Crew

Click the **Load** dropdown in the toolbar. It fetches all saved crews from the API and lists them by name. Selecting a crew loads its agents and tasks onto the canvas, resolves their edges from task-to-agent references, wraps them in a Crew Group node, and runs auto-layout.

If you have unsaved changes, a confirmation dialog asks whether to discard them before loading.

## Running a Crew

### Opening the Run Dialog

Click the green **Run** button in the toolbar. This opens the Run Dialog.

### Execution Modes

The Run Dialog has three modes, selectable via a toggle at the top:

**Run** (default). Kicks off the crew with optional JSON inputs. Calls `POST /api/v1/crews/{name}/kickoff`.

**Train**. Trains the crew over multiple iterations. Accepts an iteration count (1-100, default 3) and an output filename (default `training_data.pkl`). Calls `POST /api/v1/crews/{name}/train`.

**Test**. Tests the crew over multiple iterations. Accepts an iteration count (1-100, default 3). Calls `POST /api/v1/crews/{name}/test`.

### Crew Inputs

All three modes accept a JSON object as crew inputs. The editor validates JSON on the fly with a 300ms debounce and shows errors inline. Press `Cmd+Enter` / `Ctrl+Enter` to submit without clicking the button.

```json
{ "topic": "AI safety" }
```

### Input Presets

You can save frequently used input configurations as presets. Click "Save preset" in the Run Dialog, give it a name, and it persists in localStorage scoped to the crew name. Up to 10 presets per crew. Select a saved preset from the dropdown to fill the inputs field.

### Auto-Save Before Execution

The Studio auto-saves all nodes before starting execution. If the save fails, execution does not proceed.

### Execution Overlay

After a crew starts running, the Studio polls the execution endpoint every 3 seconds. When execution completes, task nodes and agent nodes get visual overlays:

- **Green border**: task completed successfully
- **Red border**: task failed
- Output text appears in the node data for inspection

Click "Clear results" in the toolbar to remove the execution overlay from all nodes.

Click the execution ID link in the status badge to navigate to the full execution detail page.

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Cmd/Ctrl + S` | Save crew |
| `Cmd/Ctrl + Z` | Undo |
| `Cmd/Ctrl + Shift + Z` | Redo |
| `Delete` / `Backspace` | Delete selected node |
| `Escape` | Close property panel |
| Double-click empty area | Fit view |
| `Cmd/Ctrl + /` | Show keyboard shortcuts dialog |

Undo and redo operate on a 30-snapshot history stack. They do not fire when the focus is inside a text input or textarea.

## YAML Editor

Click the YAML toggle button (file icon) in the toolbar to open a 360px-wide panel on the right side of the canvas.

The YAML editor provides bidirectional sync with the canvas:

- Changes you make on the canvas (adding nodes, editing properties) update the YAML text in real time. Position-only changes from dragging nodes do not trigger YAML updates.
- Changes you type in the YAML editor parse after a 300ms debounce and update the canvas. If parsing fails, the editor shows an "Error" badge and a red error bar at the bottom.

A status indicator in the editor header shows the current sync state: "Synced" (green check), "Parsing..." (gray), or "Error" (red).

Example YAML:

```yaml
apiVersion: blackbeard/v1
kind: Agent
metadata:
  name: researcher
spec:
  role: Researcher
  goal: Find key facts
  backstory: You research topics.
```

## Auto-Layout

Click the grid icon in the toolbar (or wait for it when loading a crew). The Studio uses ELK.js with a layered algorithm to arrange nodes left-to-right.

Layout settings:
- Algorithm: `layered`
- Direction: `RIGHT`
- Node-to-node spacing: 80px
- Between-layer spacing: 120px
- Crossing minimization: `LAYER_SWEEP`
- Edge routing: `SPLINES`

Auto-layout recalculates Crew Group bounding boxes to fit their children with padding (top: 40px, right: 20px, bottom: 20px, left: 20px). Leaf nodes that belong to a group are re-parented and repositioned relative to the group origin.

## Canvas Features

### Export

The Export dropdown in the toolbar offers two options:

- **Export JSON**: Downloads a `.json` file containing the crew name, all nodes, and all edges.
- **Copy as JSON**: Copies the same JSON structure to the clipboard.

### Minimap

A pannable, zoomable minimap appears in the bottom-right corner of the canvas. Nodes are color-coded by type (violet for agents, blue for tasks, green for tools, etc.). Hover over the minimap to increase its opacity.

### Zoom Controls

The bottom-left corner shows zoom-in, zoom-out, and fit-view buttons. The fit-view button pads the view by 50% and caps zoom at 1x.

### Snap to Grid

Nodes snap to a 20x20 pixel grid when dragged.

### Delete Keys

Both `Delete` and `Backspace` remove the selected node or edge.

### Empty Canvas

When the canvas has no nodes, an overlay shows icons for the available node types and a "Load example crew" button. The example crew contains a Researcher agent, a Writer agent, a research-topic task, and a write-report task, all wired together with edges and wrapped in a crew group.

## Collaboration

### Live Collaboration Mode

Click the radio/antenna icon in the toolbar to toggle live collaboration. When enabled and connected:

- The icon turns green with a participant count badge.
- Node additions, deletions, moves, and edge changes broadcast to all participants via WebSocket.
- Remote changes apply without creating echo loops (the hook sets an `applyingRemoteRef` flag to prevent re-broadcasting incoming changes).

When enabled but not yet connected, the icon turns amber.

### Live Cursors

With collaboration enabled, your mouse movements broadcast to other participants at ~30fps (33ms throttle). Remote cursors appear as colored arrow SVGs with name labels. The cursor overlay is pointer-events-none so it never blocks canvas interaction.

### Presence Indicators

The toolbar shows `PresenceAvatars` for users viewing the same Studio page. Presence is scoped to `studio:{crewName}` rooms via WebSocket, separate from the collaboration data channel.

## Per-Node Testing

Agent and Task nodes include a "Test Agent" or "Test Task" button at the bottom of their Property Panel form.

**How it works**:

1. The button is disabled until you fill in enough data (role or goal for agents, description for tasks).
2. Click the button. The Studio fetches available models from `GET /api/v1/models/available` and picks the first one.
3. For agents, it builds a system message from the role, goal, and backstory, then sends "Introduce yourself briefly." as the user message.
4. For tasks, it builds a prompt from the description and expected output, then asks for a sample output.
5. The result appears in a collapsible "Test Result" section with a copy-to-clipboard button.
6. Errors (no models configured, API failure) display inline.

The test uses `POST /api/v1/chat` with `max_tokens: 150`, so responses are short and fast.

## AI Assistant

Click the "Assistant" button (sparkle icon) in the toolbar to open the AI Assistant dialog. Describe what you want to build in natural language, and the assistant generates Agent, Task, and Crew resources. Click "Apply" to place the generated resources on the canvas, automatically wired with edges and wrapped in a crew group.

## Crew Settings

Click the gear icon in the toolbar to open the Crew Settings dialog. You can configure error handling behavior:

- **On Error Action**: What to do when the crew encounters an error (e.g., run a different crew).
- **On Error Crew**: Which crew to run as an error handler.

These settings save as `spec.hooks.on_error` in the Crew resource.

## Tips

- Use sticky notes to annotate your canvas. They come in four colors and do not affect crew execution.
- Double-click a Crew Component node to drill into its internal agent/task graph.
- The Property Panel's YAML tab shows a read-only preview of how the selected node will serialize. Use it to verify spec fields before saving.
- Crew names must match the pattern `^[a-z0-9][a-z0-9-]*$`. The toolbar auto-normalizes what you type.
- The browser warns you before closing the tab if you have unsaved changes.
