# PRD 08 — Guardrails & Safety

## 1. Purpose

Provide configurable safety mechanisms that validate, filter, and redact agent outputs before they reach users or downstream systems. Three subsystems: **output guardrails** (validate task results, using CrewAI's built-in guardrail system), **hallucination detection** (check factual grounding), and **PII redaction** (powered by **Microsoft Presidio**, not a custom implementation).

### 1.1 MVP Scope

**Implemented:** Task-level guardrails wired through CrewAI's built-in guardrail system, supporting three types: function-based (Python callable), LLM-based (string description evaluated by the agent's LLM), and schema-based (JSON Schema output validation). The `Guardrail` resource kind is fully working with CRUD and reference resolution. PII redaction via full Microsoft Presidio integration (`pii.py`) with configurable backends (default regex, presidio-nlp with spaCy, litellm for LLM-based detection). PII guardrail type (redact/reject/warn actions). AgentPolicy pii config (per-policy enable, entity selection, output + event redaction). PII never reaches the database.

**LLM-based PII recognizer note:** The `litellm` backend registers an `LLMPIIRecognizer` as a custom Presidio recognizer. All LLM calls for PII detection route through the LiteLLM proxy (not direct to Ollama or any provider). The recognizer sends text to a configurable model (default: `ollama/gliner-pii`) via `POST {litellm_proxy_url}/v1/chat/completions` with the master key. Responses are validated (entity type allowlist, bounds checking, score clamping) before being converted to `RecognizerResult` objects. On any LLM failure, the recognizer raises to prevent unredacted PII from being stored.

**Implemented (beyond MVP):**
- Guardrail Playground (`/guardrails/playground`): Interactive page for testing guardrails with sample input before deploying them to production tasks. Users select a guardrail resource, provide sample text, and see the validation result (pass/fail, score, feedback) in real-time. Supports function-based, LLM-based, and schema-based guardrail types.

**Implemented (post-MVP):** Namespace-level guardrails — Namespace resources support a `spec.guardrails` array of guardrail refs. At execution time, namespace guardrails are prepended to task-level guardrails (namespace guardrails run first). Configured via Namespace resource YAML or UI.

**Deferred to post-MVP:** Hallucination detection, crew-level guardrails, composite guardrail chains.

---

## 2. Output Guardrails

### 2.1 Guardrail Types

| Type | Definition | Enforcement |
|------|-----------|-------------|
| **Function-based** | Python callable returning `(bool, Any)` | Deterministic, fast |
| **LLM-based** | String description → agent's LLM evaluates | Flexible, subjective criteria |
| **Schema-based** | JSON Schema / Pydantic model validation | Structural correctness |
| **Hallucination** | Compares output against reference context for factual grounding (section 3) | LLM-evaluated with score threshold |
| **Composite** | Ordered chain of the above | Sequential pipeline |

**Performance impact**: Function-based and schema-based guardrails are near-instant (<10ms). LLM-based and hallucination guardrails each require an LLM call (typically 1-3s with a cheap model). For a crew with N tasks and M LLM-based guardrails per task, this adds up to N*M additional LLM calls (plus retries). Budget these costs when designing guardrail chains. Use `gpt-4o-mini` or equivalent for guardrail evaluation unless precision justifies a more expensive model.

### 2.2 Guardrail Resource

```yaml
apiVersion: blackbeard/v1
kind: Guardrail
metadata:
  name: word-count-limit
spec:
  type: function                      # function | llm | schema | composite
  implementation: "myproject.guardrails:validate_word_count"
  description: "Ensure output is between 100-500 words"
  max_retries: 3
  severity: error                     # error | warning | info
  # error: block execution if guardrail fails (default)
  # warning: log warning and continue execution
  # info: record result in trace but don't affect execution
  
  # For type: llm
  # prompt: |
  #   The output must be professional, factually accurate,
  #   and contain no speculation or unverified claims.
  
  # For type: schema
  # schema:
  #   type: object
  #   required: ["title", "content", "sources"]
  #   properties:
  #     title: { type: string, minLength: 10 }
  #     content: { type: string, minLength: 200 }
  #     sources: { type: array, minItems: 3 }
  
  # For type: composite
  # chain:
  #   - ref: guardrails/word-count-limit
  #   - ref: guardrails/no-profanity
  #   - "The output must be suitable for a general audience"  # inline LLM guardrail
```

The `severity` field allows deploying guardrails in observation mode before enforcing them. Deploy a new guardrail with `severity: info` to see how often it triggers, then promote to `warning`, then to `error`.

### 2.3 Guardrail Execution

```
Task output produced
    │
    ▼
┌────────────────────────────┐
│  Guardrail Pipeline        │  Execute in order; each receives prior's output
│                            │
│  guardrail[0] ──┐          │
│                 │ pass ──▶ guardrail[1] ──┐
│                 │ fail ──▶ retry          │ pass ──▶ guardrail[2] ──▶ ...
│                            │              │ fail ──▶ retry
│                            │
│  On retry:                 │
│    Feed error back to agent│
│    Agent regenerates output│
│    Re-run from failed step │
│    Up to max_retries       │
└────────────────────────────┘
```

### 2.4 Guardrail Assignment

Guardrails can be assigned at multiple levels. The examples below show field excerpts from their parent resources (Crew, Namespace). See PRD 01 for full resource schemas.

```yaml
# Per-task
tasks:
  research-ai:
    guardrails:
      - ref: guardrails/word-count-limit
      - "Must contain at least 5 sources"

# Per-crew (applies to all tasks)
crews:
  research-crew:
    default_guardrails:
      - ref: guardrails/no-pii-in-output

# Per-namespace (org-wide policy, under spec.defaults)
namespaces:
  production:
    defaults:
      guardrails:
        - ref: guardrails/no-pii-in-output
        - ref: guardrails/factual-grounding
```

Namespace-level guardrails are configured in the Namespace resource's `spec.defaults.guardrails` field (see PRD 01, section 2.10). All tasks within the namespace inherit these guardrails unless overridden at the crew or task level.

### 2.5 Guardrail Execution Order

When guardrails are assigned at multiple levels, they execute in this order:

1. **Namespace-level `defaults.guardrails`** — run first, cannot be skipped.
2. **Crew-level `default_guardrails`** — run second, apply to all tasks in the crew.
3. **Task-level `guardrails`** — run last, specific to the task.

Within each level, guardrails execute in the order they are listed. If any guardrail fails and retries are exhausted, the task fails — subsequent guardrails are not run.

**Conflict detection in `blackbeard validate`:** The validator performs basic conflict detection for obviously contradictory guardrails:
- Word count: if any guardrail requires >= N words and another requires <= M words where M < N, validation fails with a clear error
- Mutually exclusive formats: if one guardrail requires JSON output and another requires plain text, validation warns
- Duplicate detection: if the same guardrail ref appears at multiple levels (namespace + task), validation warns about redundancy

This detection is best-effort — it catches common contradictions but cannot reason about arbitrary LLM-based guardrail interactions.

Runtime conflicts that cannot be statically detected (e.g., two LLM-based guardrails with contradictory criteria) will cause the task to fail after exhausting retries. The failure message includes the full guardrail chain for debugging.

## 3. Hallucination Detection

### 3.1 HallucinationGuardrail

A specialised guardrail that compares agent output against reference context:

```yaml
apiVersion: blackbeard/v1
kind: Guardrail
metadata:
  name: factual-grounding
spec:
  type: hallucination
  llm: gpt-4o-mini                    # model used for evaluation (cheap, fast)
  threshold: 7.0                      # faithfulness score 0-10; reject below this
  context_sources:
    - task_context                    # use the task's input context
    - tool_responses                  # use tool outputs as reference
    - knowledge_sources               # use attached knowledge bases
  max_retries: 2
```

**Cost consideration**: Each hallucination check makes an LLM call to the evaluator model. For a crew with N tasks, this adds N additional LLM calls (plus retries). Use a cheap, fast model (e.g., `gpt-4o-mini`) for evaluation, and apply hallucination guardrails selectively to tasks where factual accuracy is critical — not to every task by default.

### 3.2 Evaluation Process

1. Collect reference context (task inputs, tool responses, knowledge source chunks).
2. Send output + context to evaluator LLM with a structured prompt.
3. LLM returns: `{score: 0-10, verdict: FAITHFUL|HALLUCINATED, reasons: [...]}`.
4. If score < threshold or verdict = HALLUCINATED → guardrail fails.
5. Failure feedback includes specific reasons, sent back to agent for retry.

**Default evaluation prompt**:
```
You are a factual accuracy evaluator. Compare the following agent output against the provided reference context.

Reference context:
{context}

Agent output:
{output}

Evaluate the factual faithfulness of the agent output. For each claim in the output, determine if it is:
- SUPPORTED: directly supported by the reference context
- NOT SUPPORTED: contradicted by or absent from the reference context
- AMBIGUOUS: partially supported or context is insufficient

Respond with a JSON object:
{
  "score": <0-10>,
  "verdict": "FAITHFUL" | "HALLUCINATED",
  "supported_claims": <count>,
  "unsupported_claims": <count>,
  "reasons": ["<specific claim and why it's unsupported>", ...]
}
```
This prompt can be overridden per-guardrail via the `evaluation_prompt` field on the Guardrail resource.

## 4. PII Redaction (Microsoft Presidio)

### 4.1 Overview

PII redaction is powered by **Microsoft Presidio** (MIT license, 8k+ GitHub stars), an open-source framework for detecting, redacting, and anonymizing sensitive data. Presidio runs as a **library** embedded in Blackbeard workers — no separate service needed.

**What Presidio provides (we don't build)**:
- NLP-based entity detection (spaCy models) for names, locations, organizations
- Regex-based detection for structured data (credit cards, SSNs, emails, phones, etc.)
- 20+ built-in entity recognizers
- Custom recognizer API (regex patterns + deny lists)
- Anonymizer with configurable operators (mask, redact, replace, hash, encrypt)
- Multi-language support

**What Blackbeard adds**:
- `PIIConfig` YAML resource that compiles to Presidio recognizer/anonymizer configuration
- Integration with execution event log: redact PII from event data before storage
- GUI for managing PII rules (entity toggles, custom recognizer builder)
- Per-namespace PII policies
- **LLM-based recognizer** (`LLMPIIRecognizer`): Custom Presidio `EntityRecognizer` that sends text to an LLM (e.g., GLiNER/HydroX) via the LiteLLM proxy for higher-accuracy PII detection. All LLM calls for PII recognition route through the LiteLLM proxy -- never directly to a provider. Configurable via the `backend: litellm` setting in PII config.

Ensures compliance with GDPR, HIPAA, PCI-DSS.

### 4.2 PII Configuration

```yaml
apiVersion: blackbeard/v1
kind: PIIConfig
metadata:
  name: production-pii
spec:
  enabled: true
  language: "en"                      # ISO 639-1 language code. Default: "en". Presidio supports: en, es, de, fr, it, pt, nl, he, ar, ja, zh, ko, and others.
  scope:
    traces: true                      # redact in stored traces
    outputs: false                    # optionally redact in task outputs
    logs: true                        # redact in application logs
  
  entities:
    # Global entities
    - type: CREDIT_CARD
      action: mask                    # mask | redact
    - type: EMAIL_ADDRESS
      action: mask
    - type: PHONE_NUMBER
      action: mask
    - type: PERSON
      action: mask
    - type: IP_ADDRESS
      action: mask
    
    # US-specific
    - type: US_SSN
      action: mask
    - type: US_BANK_NUMBER
      action: mask
    
    # Disabled (too many false positives)
    # - type: DATE_TIME
    # - type: LOCATION
  
  custom_recognizers:
    - name: SALARY
      type: regex
      pattern: "salary:\\s*\\$\\s*\\d{1,3}(,\\d{3})*(\\.\\d{2})?"
      action: mask
      context_words: ["salary", "compensation", "pay", "wage"]
      confidence: 0.8
    
    - name: EMPLOYEE_ID
      type: regex
      pattern: "EMP-\\d{6}"
      action: mask
    
    - name: PROJECT_CODENAME
      type: denylist
      values: ["Project Titan", "Project Phoenix", "Operation Sunrise"]
      action: redact
```

### 4.3 Presidio Integration Code Path

```python
from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
from presidio_anonymizer import AnonymizerEngine

# Blackbeard compiles PIIConfig YAML → Presidio recognizer setup
def build_presidio_engine(pii_config: PIIConfig) -> tuple:
    analyzer = AnalyzerEngine()
    
    # Add custom recognizers from PIIConfig
    for recognizer in pii_config.spec.custom_recognizers:
        if recognizer.type == "regex":
            pattern = Pattern(name=recognizer.name, regex=recognizer.pattern, score=recognizer.confidence)
            analyzer.registry.add_recognizer(
                PatternRecognizer(
                    supported_entity=recognizer.name,
                    patterns=[pattern],
                    context=recognizer.context_words,
                )
            )
    
    anonymizer = AnonymizerEngine()
    return analyzer, anonymizer

# At trace write time:
def redact_for_trace(text: str, analyzer, anonymizer, pii_config) -> str:
    entities = [e.type for e in pii_config.spec.entities if e.action != "ignore"]
    results = analyzer.analyze(text=text, entities=entities, language="en")
    return anonymizer.anonymize(text=text, analyzer_results=results).text
```

### 4.4 Redaction Examples

```
Original: "Contact john.doe@company.com or call 555-123-4567"
Redacted: "Contact <EMAIL_ADDRESS> or call <PHONE_NUMBER>"

Original: "Employee EMP-123456 salary: $125,000"
Redacted: "Employee <EMPLOYEE_ID> <SALARY>"

Original: "Credit card 4111-1111-1111-1111 was charged"
Redacted: "Credit card <CREDIT_CARD> was charged"
```

### 4.5 PII in Sandbox Context

When tools execute in sandboxed environments:
- **Inputs** to the sandbox are NOT redacted (the tool needs the real data to work).
- **Outputs** stored in traces ARE redacted according to PII config.
- **Env vars** injected into sandboxes are filtered by AgentPolicy (PRD 03), not PII rules.

**Why not redact inputs**: Tools need real data to function (e.g., a CRM lookup tool needs the actual customer email, not `<EMAIL_ADDRESS>`). PII protection for tool inputs is handled by AgentPolicy constraints -- restricting which tools can access which data -- not by redaction. See PRD 03 section 3 `data.environment_variables` and `data.knowledge_sources`.

## 5. Feature Ownership

Safety and guardrail functionality is distributed across three systems. Blackbeard orchestrates but does not reimplement features that already exist in CrewAI or LiteLLM:

| Capability | Owner | Mechanism | Blackbeard's Role |
|------------|-------|-----------|-------------------|
| **Agent output guardrails** | **CrewAI** | `Task(guardrail=callback)` / `Task(guardrails=[...])` -- built-in guardrail callbacks on Task | Expose via YAML `spec.guardrails`, compile to CrewAI guardrail callbacks at execution time |
| **Hallucination detection** | **Blackbeard** | Custom guardrail type using evaluator LLM (section 3) | Build and maintain -- CrewAI does not provide this |
| **Request/response content filtering** | **LiteLLM** | LiteLLM's guardrails feature: PII masking, content filtering, prompt injection detection | Configure via LiteLLM config; Blackbeard generates the config from `PIIConfig` resources |
| **PII redaction (traces/logs)** | **Blackbeard + Presidio** | Microsoft Presidio library embedded in workers (section 4) | Build and maintain -- redacts PII from execution event data before storage |
| **WASM sandbox isolation** | **Blackbeard** | WASM runtime with capability-based isolation (PRD 05, section 6) | Build and maintain -- unique to Blackbeard, not provided by CrewAI or LiteLLM |
| **Budget enforcement** | **LiteLLM** | Virtual key `max_budget` with real-time enforcement | Configure via AgentPolicy-to-virtual-key mapping (PRD 06) |
| **Tool access control** | **Blackbeard** | AgentPolicy allowlists/denylists (PRD 03) | Build and maintain -- enforced by Blackbeard's policy layer before tool dispatch |

**Principle:** Use the right tool for the right job. CrewAI's guardrail system handles output validation at the agent level. LiteLLM's guardrails handle request/response filtering at the LLM proxy level. Blackbeard's unique contribution is the WASM sandbox, policy enforcement, and the orchestration layer that ties everything together.

---

## 6. Safety Layers Summary

```
Agent produces output
    │
    ▼
┌────────────────────┐
│  Guardrails        │  Validate structure, content, quality
│  (section 2)       │  Retry if failed
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  Hallucination     │  Check factual grounding against context
│  Detection (section 3)   │  Retry if score below threshold
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  PII Redaction     │  Mask sensitive data before storage
│  (section 4)       │  (traces, logs — optionally outputs)
└────────┬───────────┘
         │
         ▼
  Output stored / returned to user
```

**Pipeline ordering is mandatory:** Guardrails → Hallucination Detection → PII Redaction. PII redaction is always the LAST safety layer before trace storage. Guardrails and hallucination detection operate on unredacted output. Reordering the pipeline causes incorrect guardrail failures (e.g., a guardrail checking for specific content would see redacted placeholders like `<EMAIL_ADDRESS>` instead of actual values).

## 7. Events Emitted

| Event | Payload |
|-------|---------|
| `guardrail.passed` | `{task, guardrail, score}` |
| `guardrail.failed` | `{task, guardrail, reason, retry_count}` |
| `guardrail.max_retries_exceeded` | `{task, guardrail, last_reason}` |
| `hallucination.detected` | `{task, score, verdict, reasons}` |
| `pii.redacted` | `{trace_id, entity_type, count}` |

## 8. Acceptance Criteria

1. Function-based guardrail rejects invalid output and agent retries successfully.
2. LLM-based guardrail evaluates subjective criteria and provides actionable feedback.
3. Composite guardrail chain executes in order; failure at step N retries from step N.
4. Hallucination guardrail detects unfaithful content with score below threshold.
5. PII redaction masks email, phone, SSN, credit card in traces.
6. Custom regex recognizer correctly identifies and masks domain-specific PII.
7. PII redaction does not modify tool inputs (tools receive real data).
8. Namespace-level required guardrails apply to all tasks in that namespace.
