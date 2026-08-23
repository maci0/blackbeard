# Event Storming

Domain events, commands, aggregates, read models, and policies for the Blackbeard platform. Organized by bounded context.

---

## 1. Identity and Authentication

### Commands
- `RegisterUser(email, password, display_name)`
- `LoginUser(email, password)`
- `RefreshToken(refresh_token)`
- `GenerateApiKey(user_id)`
- `RevokeApiKey(user_id)`
- `DeactivateUser(user_id)`
- `OIDCLogin(provider)`
- `OIDCCallback(code, state)`

### Domain Events
- `UserRegistered(user_id, email)`
- `UserLoggedIn(user_id, method=password|oidc|api_key)`
- `TokenRefreshed(user_id)`
- `ApiKeyGenerated(user_id)`
- `ApiKeyRevoked(user_id)`
- `UserDeactivated(user_id)`
- `SessionExpired(user_id)`
- `LoginFailed(email, reason)`

### Aggregates
- **User** (id, email, password_hash, display_name, is_active, api_key_hash)

### Policies
- Password complexity: min 8 chars, at least 1 letter and 1 digit
- API key uses HMAC comparison (constant-time)
- JWT: access token 15min, refresh token 7d
- Rate limit on auth endpoints

---

## 2. RBAC and Authorization

### Commands
- `CreateRole(name, permissions[])`
- `CreateRoleBinding(role, subject, project)`
- `DeleteRoleBinding(name)`
- `CreateGroup(name, description)`
- `AddGroupMember(group_id, user_id)`
- `RemoveGroupMember(group_id, user_id)`

### Domain Events
- `RoleCreated(name, permissions)`
- `RoleBindingCreated(role, subject, project)`
- `RoleBindingDeleted(name)`
- `GroupCreated(name)`
- `GroupMemberAdded(group_id, user_id)`
- `GroupMemberRemoved(group_id, user_id)`
- `PermissionDenied(user_id, resource_kind, verb)`

### Aggregates
- **Role** (name, permissions: [{resource, verbs}])
- **RoleBinding** (role_ref, subject_ref, project)
- **Group** (name, members[])

### Policies
- `require_permission(verb, kind)` checks on every API call
- Predefined roles: owner, admin, developer, operator, viewer, policy-admin, agent-unrestricted, agent-standard, agent-read-only
- Subject can be User, Group, Agent, or Crew

---

## 3. Resource Management

### Commands
- `CreateResource(kind, name, project, spec)`
- `UpdateResource(kind, name, spec, version)`
- `DeleteResource(kind, name)`
- `RollbackResource(kind, name, target_version)`
- `ExportResources(filter?)`
- `ImportResources(yaml_documents[])`
- `ValidateResource(kind, spec)`

### Domain Events
- `ResourceCreated(kind, name, project, version=1)`
- `ResourceUpdated(kind, name, version, changed_fields[])`
- `ResourceDeleted(kind, name)`
- `ResourceVersionSnapshot(kind, name, version, spec_snapshot)`
- `ResourceRolledBack(kind, name, from_version, to_version)`
- `ResourceValidationFailed(kind, name, errors[])`
- `ResourceRefResolved(ref_string, target_kind, target_name)`
- `ResourceRefBroken(ref_string, reason)`
- `BulkImportCompleted(created, updated, failed)`

### Aggregates
- **Resource** (kind, name, project, spec, version, labels)
- **ResourceVersion** (resource_id, version, spec_snapshot, labels_snapshot)
- **ResourceRef** (source_resource, ref_string, target_kind, target_name)

### Read Models
- Resource list (filterable by kind, project, labels)
- Resource detail with version history
- Ref dependency graph

### Policies
- Optimistic locking via `version` field on updates
- Name format: `^[a-z0-9][a-z0-9-]*$`
- Spec validated against per-kind JSON schema
- Version snapshot created on every create/update

---

## 4. Execution Engine

### Commands
- `KickoffCrew(crew_name, inputs, initiated_by)`
- `TrainCrew(crew_name, inputs, iterations)`
- `TestCrew(crew_name, inputs, iterations, model)`
- `CancelExecution(execution_id)`
- `RetryExecution(execution_id)`
- `RespondToHITL(execution_id, response)`
- `RunFlow(flow_name, inputs)`

### Domain Events
- `ExecutionCreated(id, crew_name, type=kickoff|train|test, initiated_by)`
- `ExecutionStarted(id, thread_id)`
- `ExecutionCompleted(id, duration_ms, token_usage, cost)`
- `ExecutionFailed(id, error, duration_ms)`
- `ExecutionCancelled(id, cancelled_by)`
- `ExecutionRetried(id, new_execution_id)`
- `TaskStarted(execution_id, task_name, agent_name)`
- `TaskCompleted(execution_id, task_name, output, tokens)`
- `TaskFailed(execution_id, task_name, error)`
- `HITLRequested(execution_id, task_name, prompt)`
- `HITLResponseReceived(execution_id, response)`
- `LLMCallMade(execution_id, model, prompt_tokens, completion_tokens, cost)`
- `ToolInvoked(execution_id, tool_name, success)`
- `DelegationOccurred(execution_id, from_agent, to_agent)`
- `CostAlertTriggered(execution_id, current_spend, threshold)`
- `BudgetExceeded(execution_id, limit_type=usd|tokens)`
- `VirtualKeyCreated(execution_id, budget_limits)`
- `VirtualKeyDeleted(execution_id)`

### Aggregates
- **Execution** (id, crew_name, type, status, inputs, outputs, token_usage, cost, initiated_by, principal_chain)
- **ExecutionEvent** (execution_id, event_type, data, timestamp)

### Read Models
- Execution list (filterable by status, crew, type)
- Execution detail with task breakdown
- Execution timeline (Gantt)
- Execution comparison (two side by side)
- Live execution log (SSE stream)

### Policies
- Budget enforcement: AgentPolicy max_usd/max_tokens via LiteLLM virtual keys
- Principal chain: User -> Crew -> Agent (ServiceAccount)
- Most restrictive policy across all agents wins
- HITL tasks pause execution until response received
- Each execution gets isolated asyncio event loop

---

## 5. LLM Connection and Routing

### Commands
- `CreateLLMConnection(name, provider, model, params)`
- `UpdateLLMConnection(name, spec)`
- `DeleteLLMConnection(name)`
- `TestLLMConnection(name)`
- `SyncToLiteLLM(connection)`
- `ChatStream(model, messages[])`

### Domain Events
- `LLMConnectionCreated(name, provider, model)`
- `LLMConnectionSynced(name, litellm_model_id)`
- `LLMConnectionDeleted(name, litellm_model_id)`
- `LLMConnectionTestPassed(name, latency_ms)`
- `LLMConnectionTestFailed(name, error)`
- `ChatMessageSent(model, prompt_tokens)`
- `ChatResponseStreamed(model, completion_tokens)`
- `ModelFallbackTriggered(primary_model, fallback_model, reason)`

### Aggregates
- **LLMConnection** (name, provider, model, base_url, params, fallbacks[])

### Policies
- Dynamic LiteLLM sync on create/update/delete (no restart)
- Fallback chain: try primary, then spec.fallbacks in order
- Rate limits: Agent-level `max_rpm` (CrewAI) and per-execution LiteLLM virtual keys (`tpm_limit`); connections carry no RPM/TPM fields

---

## 6. Tool Ecosystem

### Commands
- `CreateTool(name, type, spec)`
- `InstallLibraryTool(catalog_name)`
- `ImportAgencyAgents(slugs[])`
- `DiscoverMCPTools(server_config)`

### Domain Events
- `ToolCreated(name, type=python|wasm|builtin|mcp-stdio|mcp-http)`
- `LibraryToolInstalled(name, type)`
- `AgencyAgentImported(slug, division, name)`
- `AgencyAgentImportFailed(slug, reason)`
- `MCPToolDiscovered(server, tools[])`

### Aggregates
- **Tool** (name, type, source_code|command|url, sandbox_tier)
- **ToolsCatalog** (bundled YAML, read-only)
- **AgencyAgentsIndex** (division -> files[], cached 5min)

### Policies
- Tool type determines sandbox requirements
- Agency Agents API: 5min cache TTL, max 500 file cache entries
- Rate limiting on import endpoints

---

## 7. Guardrails and Safety

### Commands
- `CreateGuardrail(name, type, config)`
- `TestGuardrail(type, input_text, config)`
- `DetectPII(text, preset)`

### Domain Events
- `GuardrailCreated(name, type=function|llm|schema|pii|hallucination|composite)`
- `GuardrailTriggered(execution_id, guardrail_name, result=pass|fail)`
- `PIIDetected(entities[], preset)`
- `PIIRedacted(text_length, entity_count)`
- `GuardrailTestCompleted(type, pass, details)`

### Aggregates
- **Guardrail** (name, type, config)
- **PIIPreset** (hipaa|gdpr|pci-dss|ccpa -> entity types[])

### Policies
- Project-level guardrails prepend to task-level guardrails
- PII detection uses Presidio + optional LLM recognizer
- Trace data redacted before storage

---

## 8. Automation and Triggers

### Commands
- `CreateAutomation(name, target, trigger, inputs)`
- `TriggerAutomation(name, source=cron|webhook|api)`
- `RegisterWebhook(url, events[])`
- `DeliverWebhookEvent(webhook_id, event)`

### Domain Events
- `AutomationCreated(name, target_crew, trigger_type)`
- `AutomationTriggered(name, source, execution_id)`
- `AutomationSkipped(name, reason=max_concurrent)`
- `CronSchedulerTick(automations_checked)`
- `WebhookRegistered(id, url)`
- `WebhookDelivered(id, url, status_code, latency_ms)`
- `WebhookDeliveryFailed(id, url, error)`
- `WebhookDeleted(id)`

### Aggregates
- **Automation** (name, target, trigger, inputs, enabled, max_concurrent)
- **Webhook** (id, url, secret, events[])

### Policies
- Webhook delivery: fire-and-forget with HMAC-SHA256 signature
- Automation concurrency capped at max_concurrent
- Cron scheduler runs in FastAPI lifespan

---

## 9. Collaboration

### Commands
- `JoinCollaborationRoom(crew_name, user_id)`
- `LeaveCollaborationRoom(crew_name, user_id)`
- `BroadcastCursorPosition(crew_name, user_id, x, y)`
- `BroadcastCanvasChange(crew_name, change_type, payload)`

### Domain Events
- `UserJoinedRoom(crew_name, user_id, participant_count)`
- `UserLeftRoom(crew_name, user_id, participant_count)`
- `CursorMoved(crew_name, user_id, x, y)`
- `NodeAdded(crew_name, user_id, node_id)`
- `NodeMoved(crew_name, user_id, node_id, position)`
- `NodeDeleted(crew_name, user_id, node_id)`
- `EdgeAdded(crew_name, user_id, edge_id)`
- `EdgeDeleted(crew_name, user_id, edge_id)`

### Aggregates
- **CollaborationRoom** (crew_name, participants[], WebSocket connections)

### Policies
- Valkey pub/sub for multi-replica fan-out
- Cursor broadcast at 30fps
- Echo-loop prevention (don't send changes back to originator)

---

## 10. Observability

### Commands
- `QueryAuditLogs(filters)`
- `ExportTraces(execution_id)`
- `CheckHealth()`

### Domain Events
- `AuditLogCreated(action, resource_type, resource_id, user_id, detail)`
- `HealthCheckPassed(services[])`
- `HealthCheckDegraded(failing_service)`
- `HealthCheckFailed(failing_services[])`
- `TraceExported(execution_id, span_count)`

### Read Models
- Audit log (filterable by action, resource_type, user)
- Health status (API, PostgreSQL, Valkey, LiteLLM)
- Dashboard metrics (execution counts, resource counts, recent activity)

### Policies
- All mutations logged to `audit_logs` table
- OpenTelemetry trace export optional (via OTEL_ENDPOINT)
- Health checks: 10s interval, 120s startup grace period

---

## 11. A2A Protocol

### Commands
- `GenerateAgentCard(crew_name)`

### Domain Events
- `AgentCardGenerated(crew_name, skills[], auth_schemes[])`
- `AgentCardCacheHit(crew_name)`
- `AgentCardCacheMiss(crew_name)`

### Read Models
- Agent card JSON at `/.well-known/agent-card.json`

### Policies
- Only crews with `spec.a2a.enabled: true` generate cards
- Cards cached 60s in-memory
- Public endpoint (no auth required)

---

## Event Flow: Crew Execution (end to end)

```
User clicks "Run Crew"
  -> KickoffCrew command
  -> ExecutionCreated event
  -> VirtualKeyCreated event (budget limits from AgentPolicy)
  -> ExecutionStarted event
  |
  +-> For each task:
  |     -> TaskStarted event
  |     +-> For each LLM call:
  |     |     -> LLMCallMade event
  |     |     -> CostAlertTriggered event (if threshold crossed)
  |     |     -> BudgetExceeded event (if limit hit, execution fails)
  |     +-> For each tool use:
  |     |     -> ToolInvoked event
  |     +-> If human_input: true:
  |     |     -> HITLRequested event
  |     |     -> (pause)
  |     |     -> HITLResponseReceived event
  |     -> TaskCompleted or TaskFailed event
  |
  -> ExecutionCompleted or ExecutionFailed event
  -> VirtualKeyDeleted event
  -> WebhookDelivered event (for each registered webhook)
  -> AuditLogCreated event
```

---

## 12. Plugin System

### Commands
- `LoadPlugins(directory)`
- `ReloadPlugin(name)`
- `RegisterPlugin(meta, handler)`

### Domain Events
- `PluginDiscovered(name, type, version)`
- `PluginRegistered(name, type)`
- `PluginLoadFailed(path, error)`
- `PluginReloaded(name)`

### Aggregates
- **PluginRegistry** (plugins by type and name)

### Policies
- Directory-based auto-discovery at startup
- Graceful failure isolation (one bad plugin cannot break startup)
- Thread-safe registry with lock-always pattern
