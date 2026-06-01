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

---

## CUJ-28: Failed Execution Recovery

**Actor:** Developer user  
**Goal:** Diagnose a failed crew execution, fix the root cause, and re-run successfully  

1. Navigate to `/executions`
2. Locate an execution with `failed` status (red badge)
3. Click to open execution detail page
4. Expand the error panel to read the failure message and stack trace
5. Identify the failing task and the error cause (e.g., missing tool reference, bad prompt, provider timeout)
6. Click the crew name link to navigate to the crew's resource detail page
7. Open the YAML editor and fix the broken spec (e.g., correct the tool ref, adjust the prompt)
8. Save the updated resource, verify version increments
9. Navigate back to `/studio`, load the crew
10. Click Run, provide the same inputs as the failed execution
11. Verify the new execution completes with `completed` status
12. Compare the two executions to confirm the fix resolved the issue

**Success criteria:** Failed execution error is readable, spec fix resolves the issue, re-run succeeds.

---

## CUJ-29: Optimistic Locking Conflict

**Actor:** Two authenticated users editing the same resource concurrently  
**Goal:** Detect and resolve a version conflict when two users edit the same resource  

1. User A opens resource detail for `agents/researcher` (version 3)
2. User B opens the same resource detail (also sees version 3)
3. User A edits the backstory field and saves (version becomes 4)
4. User B edits the goal field and attempts to save (still sending version 3)
5. Backend returns `409 Conflict` because the resource version has changed
6. UI shows a conflict notification explaining the resource was modified by another user
7. User B reloads the resource to pick up User A's changes (now version 4)
8. User B re-applies their goal edit on top of the current spec
9. User B saves, version increments to 5
10. Both users' changes are preserved in the final spec

**Success criteria:** Concurrent edit detected with 409, no silent data loss, user can resolve and retry.

---

## CUJ-30: Rate Limit Handling

**Actor:** Automated client or power user  
**Goal:** Handle API rate limiting gracefully when making rapid requests  

1. Send a burst of API requests exceeding the rate limit (e.g., 150 requests in under a minute)
2. After the limit is exceeded, subsequent requests return `429 Too Many Requests`
3. Response includes `Retry-After` header indicating when to retry
4. Client pauses requests for the duration specified in the header
5. After the backoff period, resume requests
6. Verify requests succeed again with `200` responses
7. Check that no data was lost or corrupted during the rate-limited period

**Success criteria:** 429 returned with Retry-After header, requests succeed after backoff, no data loss.

---

## CUJ-31: Session Expiry and Re-authentication

**Actor:** Authenticated user with an expired JWT  
**Goal:** Re-authenticate after session expiry without losing context  

1. User is logged in and actively working (access token valid for 15 minutes)
2. User steps away, access token expires
3. User returns and performs an action (e.g., clicks Save)
4. API returns `401 Unauthorized` because the access token has expired
5. Frontend attempts silent refresh using the refresh token (valid for 7 days)
6. If refresh token is still valid: new access token issued, original action retries automatically
7. If refresh token is also expired: session expired dialog appears
8. User clicks "Log in again", redirected to `/login`
9. User logs in with credentials
10. User is redirected back to the page they were on before expiry

**Success criteria:** Silent refresh works when possible, expired session shows clear dialog, re-login preserves navigation context.

---

## CUJ-32: End-to-End Crew Lifecycle

**Actor:** Developer user  
**Goal:** Walk through the complete lifecycle of building, running, and exporting a crew  

1. Navigate to `/models`, add an LLM connection (e.g., OpenAI GPT-4)
2. Navigate to `/tools`, install a web search tool from the tools library
3. Navigate to `/studio`, create a new crew named `research-team`
4. Add an Agent node: role "Researcher", goal "Find recent data", backstory, assign the LLM connection
5. Add a Task node: description "Research topic X", expected output "Summary report", assign to the agent
6. Connect the tool to the agent node
7. Save the crew
8. Click Run, enter inputs `{"topic": "renewable energy"}`, select Run mode
9. Monitor execution progress (running state, task outputs appearing)
10. Execution completes, review per-task outputs and token/cost metrics
11. Navigate to `/executions`, verify the run appears in the list
12. Navigate to the crew's resource detail page, open the run history tab
13. Click "Re-run" on the completed execution
14. Export all resources via the export button (multi-document YAML)
15. Verify exported YAML contains the agent, task, tool ref, and crew definitions

**Success criteria:** Full lifecycle from model setup through export works without errors, all artifacts are consistent.

---

## CUJ-33: RBAC Permission Denied Flow

**Actor:** User with `developer` role  
**Goal:** Understand what happens when a restricted action is attempted  

1. Log in as a user with the `developer` role
2. Navigate to `/users` (admin-only page)
3. Verify the page shows a permission denied message or the sidebar hides the link entirely
4. Attempt to create a Role resource via the API (`POST /api/v1/roles`)
5. API returns `403 Forbidden` with an error message specifying the missing permission
6. Navigate to `/settings`, verify admin-only settings sections are hidden or disabled
7. Contact an admin user to request a role upgrade
8. Admin assigns the `admin` role to the developer user
9. Developer logs out and back in to pick up the new role
10. Verify previously restricted pages and API calls now work

**Success criteria:** 403 returned for unauthorized actions, error messages are specific, role upgrade grants access.

---

## CUJ-34: Resource Import from Git Repository

**Actor:** Authenticated user  
**Goal:** Import resources from an external git repository via the marketplace  

1. Navigate to `/marketplace`
2. Click "Import from Git"
3. Enter a git repository URL containing Blackbeard YAML resource files
4. Backend clones the repository and scans for YAML files
5. Preview screen shows discovered resources with kind, name, and validation status
6. Any validation errors are highlighted (e.g., invalid ref, missing required field)
7. Fix or deselect invalid resources
8. Click "Import Selected"
9. Resources are created via upsert (existing resources updated, new ones created)
10. If a resource name conflicts with an existing resource of the same kind, a conflict dialog appears
11. Choose to overwrite, skip, or rename the conflicting resource
12. Navigate to `/resources`, verify all imported resources are present with correct specs

**Success criteria:** Git clone, validation, conflict resolution, and upsert all work, resources appear in resource list.

---

## CUJ-35: Bulk Resource Management

**Actor:** Developer or admin user  
**Goal:** Manage multiple resources at once using bulk operations  

1. Navigate to `/resources`
2. Switch to table view if not already in table mode
3. Click the checkbox on three resources to multi-select them
4. Bulk action bar appears at the top with "Delete Selected" button
5. Click "Delete Selected", confirmation dialog appears listing the resources
6. Confirm deletion, all three resources are removed
7. Verify the resources no longer appear in the list
8. Click the YAML import button, paste a multi-document YAML string containing five resources
9. Submit, all five resources are created in a single batch
10. Verify all five appear in the resource list with correct kinds and names

**Success criteria:** Multi-select delete works, bulk YAML import creates all resources, UI updates immediately.

---

## CUJ-36: Crew with Budget Policy

**Actor:** Admin user  
**Goal:** Run a crew under a budget policy and verify spend is capped  

1. Navigate to `/resources`, create an AgentPolicy resource with `budget.max_usd: 0.50` and `budget.max_tokens: 10000`
2. Optionally set `budget.alerts.warn_at_usd: 0.30` for early warning
3. Navigate to `/studio`, create or load a crew
4. Assign the AgentPolicy to the crew's agents (via spec or property panel)
5. Save the crew
6. Run the crew with a prompt that would normally exceed the budget
7. During execution, verify a `cost_alert` event fires when spend crosses the warning threshold
8. Execution either completes within budget or fails with a budget-exceeded error
9. Navigate to execution detail, verify token usage and cost are reported
10. Verify the LiteLLM virtual key was created with the correct budget limits and deleted after execution

**Success criteria:** Budget limits enforced, warning alert fires at threshold, spend data visible in execution detail.

---

## CUJ-37: Crew with Guardrails

**Actor:** Developer user  
**Goal:** Attach guardrails to a task and verify they trigger during crew execution  

1. Navigate to `/guardrails/playground`, create and test a PII guardrail (e.g., block SSN patterns)
2. Navigate to `/resources`, create a Guardrail resource with the tested configuration
3. Navigate to `/studio`, load or create a crew
4. Select a Task node, open the property panel
5. Add the guardrail reference to the task's `guardrails` array
6. Save the crew
7. Run the crew with input that contains PII data matching the guardrail pattern
8. During execution, the guardrail triggers and either redacts the content or blocks the task
9. Navigate to execution detail, verify `guardrail_triggered` events appear in the execution log
10. View the guardrail event details showing which rule matched and what action was taken

**Success criteria:** Guardrail triggers during execution, event logged with match details, task output is filtered/blocked.

---

## CUJ-38: Crew with Knowledge Sources

**Actor:** Developer user  
**Goal:** Attach a knowledge source to an agent and verify RAG retrieval during execution  

1. Navigate to `/knowledge`, create a knowledge source (e.g., text type with product FAQ content)
2. Configure the vector store provider and save
3. Navigate to `/studio`, load or create a crew
4. Select an Agent node, open the property panel
5. Add the knowledge source reference to the agent's spec
6. Add a Task that asks a question answerable from the knowledge source content
7. Save the crew
8. Run the crew with appropriate inputs
9. Execution completes, the task output references or incorporates content from the knowledge source
10. Verify execution events show knowledge retrieval activity

**Success criteria:** Knowledge source attached, RAG retrieval occurs during execution, task output reflects sourced content.

---

## CUJ-39: Flow Execution

**Actor:** Developer user  
**Goal:** Create and execute a multi-step flow with sequential step execution  

1. Navigate to `/studio`, create a new Flow
2. Add FlowStep nodes to the canvas representing sequential stages (e.g., "Research", "Analyze", "Report")
3. Each FlowStep references a different crew or task
4. Connect FlowSteps in order using edges to define execution sequence
5. Optionally add a Condition node between steps (e.g., skip "Report" if "Analyze" finds no data)
6. Save the flow
7. Navigate to `/studio` toolbar, click Run, select the flow
8. Enter inputs and start the flow execution
9. Monitor execution progress as each step completes sequentially
10. Verify each step's output is available and feeds into the next step as expected
11. If a condition node is present, verify the conditional branch was evaluated correctly

**Success criteria:** Flow executes steps in order, condition routing works, each step's output is accessible.

---

## CUJ-40: Webhook Event Delivery

**Actor:** Admin user  
**Goal:** Register a webhook endpoint and verify execution events are delivered with valid HMAC signatures  

1. Navigate to `/webhooks`
2. Click "Add Webhook", enter the destination URL (e.g., a RequestBin or local test server)
3. Optionally filter to specific event types (e.g., `execution.completed`, `execution.failed`)
4. Save the webhook, note the HMAC secret displayed
5. Navigate to `/studio`, run a crew
6. Execution starts and progresses through tasks
7. On the webhook receiver, verify event payloads arrive for each execution lifecycle event
8. Validate the `X-Signature` header on each payload by computing HMAC-SHA256 with the secret
9. Verify the payload body contains execution ID, event type, timestamp, and relevant data
10. Run a second execution that fails, verify a `execution.failed` event is delivered
11. Delete the webhook via `/webhooks`, run another execution, verify no events are delivered

**Success criteria:** Events delivered to webhook URL, HMAC signature validates, event filtering works, deletion stops delivery.

---

## CUJ-41: HITL Interaction

**Actor:** Developer user  
**Goal:** Handle a human-in-the-loop prompt during crew execution  

1. Navigate to `/studio`, create or load a crew
2. Select a Task node, enable `human_input: true` in the property panel
3. Save the crew
4. Run the crew with appropriate inputs
5. Execution starts, progresses until it reaches the HITL task
6. Execution status changes to indicate it is waiting for human input
7. A `hitl_request` event appears in the execution log with the prompt text
8. In the execution detail page, an input form appears asking for the human response
9. Enter a response and submit via `POST /executions/{id}/respond`
10. Execution resumes with the human response incorporated
11. A `hitl_response` event is logged with the submitted text
12. Execution completes, task output reflects the human input

**Success criteria:** Execution pauses at HITL task, prompt displayed, response submitted and incorporated, execution completes.

---

## CUJ-42: User Lifecycle

**Actor:** Admin user  
**Goal:** Manage a user from invitation through deactivation  

1. Navigate to `/users`, click "Invite User"
2. Enter email, display name, and initial role (e.g., `developer`)
3. Submit, user appears in the user list with `invited` status
4. New user receives invitation, registers with the provided email
5. User status changes to `active` after registration
6. Admin navigates to the user's detail page
7. Admin assigns an additional role (e.g., `operator`)
8. Verify the user now has both `developer` and `operator` permissions
9. Admin deactivates the user account
10. User status changes to `inactive`
11. Deactivated user attempts to log in, receives an "account deactivated" error
12. Admin reactivates the user, user can log in again

**Success criteria:** Full lifecycle (invite, activate, role assignment, deactivate, reactivate) works, deactivated users cannot authenticate.

---

## CUJ-43: API Key Management

**Actor:** Authenticated user  
**Goal:** Generate a personal API key, use it for authentication, then revoke it  

1. Navigate to `/settings` or call `POST /api/v1/auth/api-key`
2. Generate a new personal API key
3. API key value is displayed once (not retrievable after dismissal)
4. Copy the API key
5. Make an API request using `X-API-Key` header with the generated key
6. Verify the request succeeds and returns the expected data
7. Verify the key identifies the correct user in audit logs
8. Revoke the API key via `DELETE /api/v1/auth/api-key` or the UI
9. Attempt to use the revoked key for an API request
10. Verify the request returns `401 Unauthorized`

**Success criteria:** Key generated and shown once, authenticates requests, revocation immediately prevents further use.

---

## CUJ-44: Resource Version Rollback

**Actor:** Developer or admin user  
**Goal:** Roll back a resource to a previous version after a bad update  

1. Navigate to `/resources`, select a resource (e.g., `agents/researcher`)
2. Note the current spec and version number (e.g., version 5)
3. Edit the resource spec, introduce an intentional change (e.g., change the goal text)
4. Save, version increments to 6
5. Realize the change was a mistake
6. Navigate to the resource's version history tab
7. View the list of versions with timestamps and spec snapshots
8. Click on version 5 to view its spec details
9. Click "Rollback to this version" (calls `POST /{kind}/{name}/rollback`)
10. Confirm the rollback in the dialog
11. Resource spec reverts to the version 5 content, version number increments to 7
12. Verify the rollback is logged in the audit trail

**Success criteria:** Version history is browsable, rollback restores the old spec, new version is created (not overwritten), audit log records the rollback.

---

## CUJ-45: Dark Mode Toggle

**Actor:** Authenticated user  
**Goal:** Switch between light and dark themes and verify consistent rendering  

1. Open the application in light mode (default)
2. Click the theme toggle in the sidebar (or navigate to `/settings`)
3. Select dark mode
4. Verify the color scheme changes immediately (background, text, borders, cards)
5. Navigate to `/studio`, verify the canvas, nodes, edges, and property panel use dark colors
6. Navigate to `/chat`, verify message bubbles and input area render correctly in dark mode
7. Navigate to `/executions`, verify table rows, status badges, and metric cards are legible
8. Navigate to `/models`, verify model cards and provider badges have appropriate contrast
9. Refresh the page, verify dark mode persists (saved in localStorage or user preferences)
10. Toggle back to light mode, verify all pages return to the original color scheme

**Success criteria:** Theme toggle applies across all pages, no contrast or readability issues, preference persists across sessions.

---

## CUJ-46: Mobile Responsive Layout

**Actor:** Authenticated user on a mobile device or narrow viewport  
**Goal:** Use the application on a small screen without layout breakage  

1. Resize the browser viewport to 375px width (mobile portrait)
2. Verify the sidebar collapses into a hamburger menu
3. Tap the hamburger menu, verify sidebar slides in as an overlay
4. Navigate to `/resources`, verify the resource list stacks vertically
5. Navigate to a resource detail page, verify the content is scrollable and not clipped
6. Navigate to `/executions`, verify the table scrolls horizontally or switches to a card layout
7. Navigate to `/studio`, verify a message indicates that the visual editor requires a wider viewport (or that it functions with pan/zoom on touch)
8. Verify all buttons and interactive elements meet minimum touch target size (44x44px)
9. Resize back to desktop width (1440px), verify the layout restores to full sidebar and multi-column views
10. Verify no horizontal overflow or content overlap at any intermediate width

**Success criteria:** Layout adapts to mobile viewport, navigation is accessible, no content is hidden or broken, touch targets are adequate.

---

## CUJ-47: 404 and Error Pages

**Actor:** Any user  
**Goal:** Encounter error pages for invalid routes and verify graceful handling  

1. Navigate to a URL that does not match any route (e.g., `/this-page-does-not-exist`)
2. Verify a 404 page is displayed with a clear "Page not found" message
3. Verify the 404 page includes a link or button to return to the dashboard
4. Click the "Go to Dashboard" link, verify navigation to `/`
5. Navigate to a valid resource detail page with a nonexistent resource name (e.g., `/resources/agents/nonexistent-agent-xyz`)
6. Verify a "Resource not found" message is displayed (not a blank page or a crash)
7. Use the browser back button, verify navigation returns to the previous page
8. Trigger a server error by requesting a malformed API endpoint
9. Verify the UI displays a generic error message (not a raw stack trace or JSON blob)
10. Verify the error page does not expose internal implementation details (file paths, server versions)

**Success criteria:** 404 page renders for unknown routes, resource-not-found handled gracefully, error pages are user-friendly and do not leak internals.
