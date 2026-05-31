# Critical User Journeys (CUJs)

Every journey below is a sequence a real user would follow to accomplish a goal. Each journey maps to one or more E2E test specs in `frontend/e2e/`.

---

## CUJ-01: First-Time Onboarding

**Actor:** New user, no account  
**Goal:** Register, log in, get oriented  

1. Navigate to `/register`
2. Fill display name, email, password (min 8 chars)
3. Submit, get redirected to `/login`
4. Log in with credentials
5. Welcome dialog appears (first visit)
6. Choose "Take the Tour" or "Skip"
7. If tour: guided overlay highlights sidebar, studio, palette, property panel
8. Tour completes, localStorage flags set
9. Land on `/studio` with empty canvas

**Success criteria:** User is authenticated, tour completed or skipped, can navigate freely.

---

## CUJ-02: Build a Crew in Studio

**Actor:** Authenticated user  
**Goal:** Create a working crew from scratch using the visual editor  

1. Navigate to `/studio`
2. Type a crew name in the toolbar input
3. Drag an Agent node from the palette onto the canvas
4. Click the Agent node, fill role/goal/backstory in property panel
5. Drag a Task node from the palette
6. Click the Task node, fill description/expected_output
7. Connect Agent to Task (drag from agent output handle to task input handle)
8. Click Save in the toolbar
9. Verify resources appear in `/resources`

**Success criteria:** Crew saved with at least one agent and one task, resources visible in resource list.

---

## CUJ-03: Run a Crew and View Results

**Actor:** Authenticated user with a saved crew  
**Goal:** Execute a crew and see outputs  

1. Navigate to `/studio`, load a crew
2. Click Run in the toolbar
3. RunDialog opens, select "Run" mode
4. Enter input JSON (e.g., `{"topic": "AI agents"}`)
5. Click "Run Crew"
6. Execution starts, redirect to execution view
7. Poll for status (running, completed, failed)
8. View per-task outputs, token usage, cost
9. Verify execution appears in `/executions`

**Success criteria:** Execution completes, results visible with token/cost metrics.

---

## CUJ-04: Train and Test a Crew

**Actor:** Authenticated user with a saved crew  
**Goal:** Train for iterative improvement, test for quality evaluation  

1. Navigate to `/studio`, load a crew
2. Click Run, select "Train" mode
3. Set iterations count, provide input
4. Click "Train Crew", verify training execution starts
5. Repeat with "Test" mode
6. Verify test results include LLM judge scores
7. Check execution list shows both train and test runs

**Success criteria:** Train and test executions complete, different execution types visible.

---

## CUJ-05: YAML Resource Management

**Actor:** Developer user  
**Goal:** Create, edit, export resources via YAML  

1. Navigate to `/resources`
2. Click import (YAML file or paste)
3. Paste multi-document YAML (Agent + Task + Crew)
4. Resources created, appear in list
5. Click a resource to open detail page
6. View YAML tab, verify spec matches
7. Edit spec via YAML editor
8. Save, verify version incremented
9. Export all resources via export button
10. Navigate to version history tab, verify snapshot

**Success criteria:** Resources created via YAML, editable, versionable, exportable.

---

## CUJ-06: Model Configuration

**Actor:** Admin user  
**Goal:** Add LLM provider connections  

1. Navigate to `/models`
2. Click "Add Connection"
3. Fill provider (openai/anthropic/vertex_ai/ollama), model name, API key
4. Optional: set temperature, max_tokens, fallbacks
5. Save, model card appears with provider badge
6. Click "Test" on model card
7. Verify connectivity test passes or shows error
8. Navigate to `/chat`, select the model
9. Send a message, verify streaming response

**Success criteria:** LLM connection created, test passes, usable in chat.

---

## CUJ-07: RBAC and User Management

**Actor:** Admin user  
**Goal:** Create users, assign roles, enforce permissions  

1. Navigate to `/users`
2. Click "Invite User"
3. Fill email, name, optional role
4. Submit, user appears in list
5. Navigate to `/roles`
6. View predefined roles (owner, admin, developer, operator, viewer)
7. Create a custom role with specific resource/verb permissions
8. Navigate back to users, assign role to user
9. Log out, log in as new user
10. Verify restricted pages show permission errors

**Success criteria:** User created, role assigned, permissions enforced.

---

## CUJ-08: Marketplace Import

**Actor:** Authenticated user  
**Goal:** Import pre-built crews from the marketplace  

1. Navigate to `/marketplace`
2. Browse built-in example crews (research, code-review, etc.)
3. Click preview to see crew details
4. Click "Import" on a crew
5. Verify resources created (agents, tasks, crew)
6. Navigate to `/studio`, load the imported crew
7. Canvas shows the crew's agents and tasks

**Success criteria:** Marketplace crew imported, visible in studio.

---

## CUJ-09: Tool Management

**Actor:** Authenticated user  
**Goal:** Browse, install, and manage tools  

1. Navigate to `/tools`
2. View existing tools with type badges (python, builtin, mcp-stdio, etc.)
3. Navigate to `/tools/library`
4. Browse catalog, search for a tool
5. Click "Install" on a tool
6. Tool appears in `/tools` list
7. Navigate to `/studio`, drag a Tool node
8. Connect tool to an agent
9. Save crew with tool reference

**Success criteria:** Tool installed from library, attached to agent in crew.

---

## CUJ-10: Agency Agents Import

**Actor:** Authenticated user  
**Goal:** Import agent personas from Agency Agents library  

1. Call agency agents browse API or use UI import
2. Filter by division (engineering, design, etc.)
3. Select agents to import
4. Agents created as Blackbeard Agent resources
5. Agents have `source: agency-agents` label
6. Agents visible in `/resources` filtered by Agent kind

**Success criteria:** External agent personas imported and available.

---

## CUJ-11: Automation Setup

**Actor:** Admin user  
**Goal:** Schedule recurring crew executions  

1. Navigate to `/automations`
2. Click "Create Automation"
3. Select target crew, trigger type (cron/webhook/api)
4. For cron: enter cron expression
5. For webhook: get HMAC secret
6. Set inputs and max concurrency
7. Save automation
8. Verify automation appears in list
9. For webhook: trigger via curl with HMAC signature

**Success criteria:** Automation created, trigger works.

---

## CUJ-12: Webhook Management

**Actor:** Admin user  
**Goal:** Register webhooks for execution event delivery  

1. Navigate to `/webhooks`
2. Click "Add Webhook"
3. Enter URL and optional events filter
4. Webhook created, secret shown
5. Run a crew execution
6. Verify webhook receives events with HMAC signature

**Success criteria:** Webhook registered, events delivered.

---

## CUJ-13: Guardrail Testing

**Actor:** Developer user  
**Goal:** Test guardrails before deploying to tasks  

1. Navigate to `/guardrails/playground`
2. Select guardrail type (function, LLM, schema, PII)
3. For PII: select compliance preset (HIPAA, GDPR, etc.)
4. Enter sample text with PII data
5. Click "Run Test"
6. View detection results, redacted output
7. Iterate on guardrail config until satisfied

**Success criteria:** Guardrail tested, expected PII detected/redacted.

---

## CUJ-14: Credential Management

**Actor:** Admin user  
**Goal:** Store and manage secrets  

1. Navigate to `/credentials`
2. Click "Add Credential"
3. Enter name, type (api_key, token, etc.), value
4. Save, credential appears with masked value
5. Verify value is not visible after creation
6. Delete credential, verify removed

**Success criteria:** Credential stored securely, masked in UI.

---

## CUJ-15: Project Management

**Actor:** Admin user  
**Goal:** Create projects for resource isolation  

1. Navigate to `/projects`
2. Click "Create Project"
3. Enter project name (lowercase, hyphens only)
4. Save, project appears in list
5. Use project switcher in sidebar to switch context
6. Create resources in new project
7. Switch back to default, verify new resources not visible

**Success criteria:** Project created, resource isolation works.

---

## CUJ-16: Execution Comparison

**Actor:** Developer user  
**Goal:** Compare two executions side by side  

1. Navigate to `/executions`
2. Select two completed executions
3. Click "Compare"
4. View side-by-side metrics (duration, tokens, cost)
5. View per-task output diff

**Success criteria:** Comparison page shows metric diffs.

---

## CUJ-17: Audit Trail Review

**Actor:** Admin user  
**Goal:** Review all mutations for compliance  

1. Navigate to `/audit-logs`
2. View mutation history (resource creates/updates/deletes)
3. Filter by resource type, action, user
4. Click an entry to see details
5. Verify all mutations logged (no gaps)

**Success criteria:** Complete audit trail visible and filterable.

---

## CUJ-18: Knowledge Source Management

**Actor:** Developer user  
**Goal:** Add RAG content for agents  

1. Navigate to `/knowledge`
2. Click "Add Knowledge Source"
3. Select source type (text, PDF, CSV, JSON, URL)
4. Upload or enter content
5. Configure vector store provider
6. Save, knowledge source appears with type badge
7. Attach knowledge source to an agent in Studio

**Success criteria:** Knowledge source created, attachable to agents.

---

## CUJ-19: Chat Playground

**Actor:** Authenticated user  
**Goal:** Interact with LLMs directly  

1. Navigate to `/chat`
2. Select an LLM connection from dropdown
3. Type a message
4. Verify streaming response renders token by token
5. Click stop button during generation
6. Verify generation stops
7. Continue conversation with follow-up message

**Success criteria:** Streaming chat works with stop capability.

---

## CUJ-20: Settings and Preferences

**Actor:** Authenticated user  
**Goal:** Configure personal preferences  

1. Navigate to `/settings`
2. Set default project
3. Configure notification preferences
4. Toggle sound settings
5. Verify settings persist across page reloads
6. Toggle dark mode from sidebar
7. Verify theme applies correctly

**Success criteria:** Preferences saved and applied.

---

## CUJ-21: Command Palette Navigation

**Actor:** Authenticated user  
**Goal:** Navigate quickly via keyboard  

1. Press Cmd+K (or Ctrl+K)
2. Command palette opens
3. Type "exec" to fuzzy-search
4. Select "Executions" from results
5. Navigate to executions page
6. Press Cmd+K again, type a resource name
7. Navigate to resource detail

**Success criteria:** Command palette enables fast navigation.

---

## CUJ-22: Keyboard Shortcuts

**Actor:** Power user  
**Goal:** Use keyboard shortcuts for common actions  

1. Press `?` to open shortcuts dialog
2. Review available shortcuts
3. Close dialog
4. Press Cmd+Shift+S to go to Studio
5. Press Cmd+Shift+E to go to Executions
6. Press Cmd+Shift+N to go to Resources
7. Press Cmd+. to go to Settings

**Success criteria:** All documented shortcuts work.

---

## CUJ-23: Observability Dashboard

**Actor:** Admin or developer user  
**Goal:** Monitor platform health, spend, and execution metrics at a glance  

1. Navigate to `/observability`
2. View budget utilization cards (current spend, remaining budget, spend rate)
3. View execution metrics (total runs, success rate, average duration, active count)
4. View token usage breakdown by crew
5. View policy and safety stats (permission denials, guardrail triggers, budget exceeded events)
6. Click a stat card to navigate to the related detail page (e.g., click spend to go to executions, click guardrail triggers to go to guardrails)

**Success criteria:** Dashboard renders all metric groups, cards link to correct detail pages.

---

## CUJ-24: Plugin Management

**Actor:** Admin user  
**Goal:** Install, reload, and use plugins that extend tools or guardrails  

1. Browse installed plugins via `GET /api/v1/plugins`
2. Place a plugin file (Python module) in the `plugins/` directory
3. Restart the server, or call `POST /api/v1/plugins/{name}/reload` to hot-reload
4. Verify the plugin appears in the listing with correct type and version
5. Create or update a crew that references the custom tool or guardrail provided by the plugin
6. Run the crew and confirm the plugin's tool or guardrail executes

**Success criteria:** Plugin discovered, registered, and functional in crew execution.

---

## CUJ-25: Git Version Control

**Actor:** Developer or admin user  
**Goal:** Track resource changes through git-backed version control  

1. Create or update a resource (triggers a git commit on the backing repo)
2. View git log at `GET /api/v1/git/log` to see commit history
3. View diff between two commits to inspect what changed
4. View blame for a specific resource file to see who changed each line
5. View resource content at a specific commit to inspect historical state
6. Add a remote via `POST /api/v1/git/remotes` and push to sync with an external repository

**Success criteria:** Resource mutations produce git commits, history is browsable, push to remote works.

---

## CUJ-26: Interactive TUI Shell

**Actor:** Developer or operator user  
**Goal:** Manage resources and run crews from an interactive terminal session  

1. Run `blackbeard shell` to enter the TUI
2. Use tab completion for commands and resource names
3. Run `ls Agent` to list all agents
4. Run `get Agent researcher` to view an agent's details
5. Run `run research-crew` to kick off a crew execution
6. Run `watch <execution-id>` to stream execution events in real time
7. Run `use production` to switch the active project context

**Success criteria:** Shell launches, completions work, CRUD and execution commands operate correctly.

---

## CUJ-27: Temporal Workflow Execution

**Actor:** Admin or operator user  
**Goal:** Run crew executions as durable Temporal workflows with automatic retry  

1. Set the `TEMPORAL_HOST` environment variable to point at a Temporal cluster
2. Start the Temporal services via `docker-compose.temporal.yaml`
3. Kick off a crew execution through the API or UI
4. Open the Temporal UI at `:8233` and verify the workflow appears
5. Simulate a failure mid-execution and confirm Temporal retries the workflow according to its retry policy

**Success criteria:** Execution runs as a Temporal workflow, visible in Temporal UI, retries on failure.
