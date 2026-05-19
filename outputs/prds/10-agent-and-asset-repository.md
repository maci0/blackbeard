# PRD 10 — Agent & Asset Repository

## 1. Purpose

Provide a shared, versioned library of reusable agents, tasks, tools, crews, flows, guardrails, and templates. Teams can publish, discover, fork, and compose assets without duplicating work. The repository is the internal marketplace.

### 1.1 MVP Scope

**Implemented:** Git-based asset management via `blackbeard export --all -o repo/` and `blackbeard apply -f repo/`. Marketplace import from git repositories (clone and apply). Versioning via git commits. Sharing via git push/pull.

**Deferred to post-MVP:** No MinIO, no custom registry (`repository_assets` table), no publishing UI, no `blackbeard repo publish/install` commands, no approval workflows, no semver resolution. The full repository system described in this PRD remains post-MVP.

## 2. Asset Types

| Asset Kind | Description | Example |
|------------|-------------|---------|
| **Agent** | Reusable agent definition | `market-research-agent`, `code-reviewer` |
| **Task** | Reusable task template | `summarise-document`, `extract-entities` |
| **Tool** | Published tool package (Python or WASM) | `serper-search@1.2.0`, `pdf-parser.wasm@0.3.0` |
| **Crew** | Pre-composed crew with agents + tasks | `content-pipeline`, `support-triage` |
| **Flow** | Pre-composed flow with steps | `onboarding-flow`, `invoice-processing` |
| **Guardrail** | Reusable validation logic | `no-pii-in-output`, `word-count-limit` |
| **Template** | Starter project scaffold | `research-crew-template`, `flow-quickstart` |
| **Sandbox** | Sandbox profile | `high-isolation`, `wasm-default` |
| **AgentPolicy** | Reusable policy | `standard`, `restricted`, `hardened` |

## 3. Repository Structure

```
repository/
├── agents/
│   ├── market-research-agent/
│   │   ├── agent.yaml
│   │   ├── README.md
│   │   ├── CHANGELOG.md
│   │   └── versions/
│   │       ├── 1.0.0/
│   │       ├── 1.1.0/
│   │       └── 2.0.0/  (latest)
│   └── ...
├── tools/
│   ├── sentiment-analyzer/
│   │   ├── tool.yaml
│   │   ├── tool.wasm          # WASM binary
│   │   ├── wit/tool.wit
│   │   └── README.md
│   └── ...
├── crews/
├── flows/
├── guardrails/
└── templates/
```

**Storage backend**: Repository assets are stored in MinIO (S3-compatible) with the following bucket layout:

```
s3://blackbeard-repo/
├── agents/
│   └── market-research-agent/
│       ├── 1.0.0/
│       │   ├── agent.yaml
│       │   ├── README.md
│       │   └── metadata.json         # version metadata, checksums, dependencies
│       └── 2.0.0/
│           └── ...
├── tools/
│   └── sentiment-analyzer/
│       └── 0.3.0/
│           ├── tool.yaml
│           ├── tool.wasm
│           └── metadata.json
└── ...
```

The repository index (searchable catalogue of all published assets) is stored in PostgreSQL for fast querying. MinIO stores the actual asset files. `metadata.json` is generated at publish time and includes: version, author, description, tags, dependencies, checksums (SHA-256), and publish timestamp.

**Database schema (repository index):**
```sql
repository_assets
  id              UUID PK DEFAULT gen_random_uuid()
  kind            VARCHAR(32) NOT NULL     -- Agent, Tool, Crew, etc.
  name            VARCHAR(255) NOT NULL
  version         VARCHAR(32) NOT NULL     -- semver: 1.0.0, 2.1.0-beta
  status          VARCHAR(16) NOT NULL DEFAULT 'active'  -- active | deprecated | yanked
  author          VARCHAR(255)
  description     TEXT
  tags            TEXT[]                   -- PostgreSQL array
  dependencies    JSONB                    -- [{kind, name, version_range}]
  checksums       JSONB                    -- {sha256: '...'}
  artifact_url    TEXT NOT NULL            -- MinIO URL: s3://blackbeard-repo/...
  download_count  INTEGER NOT NULL DEFAULT 0
  deprecation_msg TEXT                     -- set when status = deprecated
  replacement_ref TEXT                     -- suggested replacement asset ref
  published_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  published_by    VARCHAR(255)

  UNIQUE(kind, name, version)

Indexes:
  idx_repo_search ON repository_assets(kind, status)
  idx_repo_tags   ON repository_assets USING GIN(tags)
  idx_repo_name   ON repository_assets(name)
```

## 4. Publishing

```bash
# Publish an agent to the repository
blackbeard repo publish agents/market-research-agent/ \
  --version 2.0.0 \
  --description "Market research agent with web search and analysis" \
  --tags "research,market,analysis"

# Publish a WASM tool
blackbeard repo publish tools/sentiment-analyzer/ \
  --version 0.3.0 \
  --artifact tool.wasm
```

### 4.1 Publication Workflow

1. **Validate**: `blackbeard validate` on all resource files.
2. **Test** (optional): Run automated tests if defined.
3. **Package**: Bundle YAML + artifacts (WASM binaries, Python packages).
4. **Version**: Assign semver, check for breaking changes.
5. **Review** (optional): If org requires approval, submit for admin review.
6. **Publish**: Store in repository, update index.

### 4.2 Approval Workflow

Configurable per-org:

| Mode | Behaviour |
|------|-----------|
| **Open** | Anyone with `create` permission on the asset kind can publish |
| **Review** | Publication requires approval from a user with `approve` permission |
| **Locked** | Only admins can publish; all others submit proposals |

## Asset Lifecycle

Published assets have a lifecycle status:

| Status | Visibility | Behavior |
|--------|-----------|----------|
| `active` | Visible in search, installable | Normal operation |
| `deprecated` | Visible with warning banner, installable with CLI warning | `blackbeard repo install` prints: "WARNING: {asset} is deprecated. Reason: {message}. Suggested replacement: {ref}" |
| `yanked` | Hidden from search, existing references show warning | Cannot be newly installed. Existing references continue to work but `blackbeard validate` emits a warning. Used for security vulnerabilities. |

Deprecation and yanking are performed by asset publishers or org admins:
```bash
blackbeard repo deprecate tools/old-search@1.0.0 --reason "Use tools/new-search instead" --replacement tools/new-search@2.0.0
blackbeard repo yank tools/vulnerable-tool@0.5.0 --reason "CVE-2026-XXXX: Remote code execution"
```

## 5. Consuming Assets

### 5.1 Reference in YAML

```yaml
# Use a repository agent by ref
spec:
  agents:
    - ref: repo:agents/market-research-agent@2.0.0
    - ref: repo:agents/code-reviewer@latest
```

### 5.2 CLI Install

```bash
# Install a tool from repository into current project
blackbeard repo install tools/sentiment-analyzer@0.3.0

# Install a crew template
blackbeard repo install templates/research-crew-template --as my-research-crew
```

### 5.3 Override on Use

Repository assets can be overridden at the point of use:

```yaml
spec:
  agents:
    - ref: repo:agents/market-research-agent@2.0.0
      overrides:
        goal: "Research trends in renewable energy"
        tools:
          - ref: tools/custom-energy-db      # add a project-specific tool
```

**Merge semantics**: Overrides use **shallow merge at the `spec` level** — each top-level key in `overrides` replaces the corresponding key in the repository asset's `spec`. Nested objects are replaced entirely, not deep-merged.

| Repository asset | Override | Effective result |
|-----------------|----------|------------------|
| `tools: [A, B, C]` | `tools: [D]` | `tools: [D]` (replaced) |
| `goal: "Research trends"` | `goal: "Research energy"` | `goal: "Research energy"` (replaced) |
| `checkpoint: {enabled: true, max: 10}` | `checkpoint: {enabled: false}` | `checkpoint: {enabled: false}` (`max` is lost — full replace) |
| `memory: true` | (not in overrides) | `memory: true` (unchanged) |

**Warning:** Overriding a list field (e.g., `tools`) replaces the entire list, not extends it. To add a tool to a repository agent's existing tool list, you must include the original tools plus your addition in the override.

To extend a list rather than replace it, use the `extend` syntax:
```yaml
overrides:
  tools:
    extend:
      - ref: tools/custom-energy-db    # appended to repository asset's tools list
```

### 5.4 Fork

Fork creates a mutable copy of a repository asset in the user's project:

```bash
blackbeard repo fork agents/market-research-agent@2.0.0 --as my-research-agent
```

The forked asset is a standalone resource — it has no link back to the original. Changes to the original do not propagate. This is intentional: forks are for customization, not tracking.

To stay in sync with upstream, use `ref: repo:` with `overrides` (section 5.3 of this PRD) instead of forking.

## 6. Discovery (UI)

### 6.1 Browse

- **Grid/List view** of all published assets.
- **Category tabs**: Agents, Tasks, Tools, Crews, Flows, Guardrails, Templates.
- **Tags**: Filterable tag chips.
- **Sorting**: By name, popularity (install count), last updated, version count.

### 6.2 Asset Detail Page

- Name, description, author, tags, version history.
- **README**: Rendered markdown documentation.
- **YAML preview**: Full resource definition.
- **Dependencies**: What this asset requires (tools, knowledge sources).
- **Dependents**: What uses this asset (crews, automations).
- **Usage metrics**: Install count, execution count, avg rating.
- **Install button**: One-click install into current project.

### 6.3 Search

- Fuzzy search across name, description, tags, README content.
- Filter by asset kind, author, org, version range.

## 7. Versioning

- **Semver**: All assets use semantic versioning.
- **`@latest`**: Resolves to the highest published version.
- **`@1.x`**: Resolves to the highest `1.*.*` version (compatible range).
- **`@1.2.0`**: Pins to exact version.
- **Breaking change detection**: When publishing a new major version, the system checks for dependents that may break.
- **Dependency resolution (post-v1)**: Transitive dependency resolution (e.g., installing a crew automatically installs its referenced agents) is deferred to post-v1. For v1, all dependencies must be pinned to exact versions and installed explicitly:

```bash
# v1: explicit install of all dependencies
blackbeard repo install agents/researcher@1.2.0
blackbeard repo install tools/serper-search@2.0.0
blackbeard repo install crews/research-crew@1.0.0   # references the above
```

**v1 constraint:** Transitive dependency resolution with semver ranges is post-v1. For v1, all repository references must pin exact versions (`@2.0.0`, not `@^2.0.0`). The `@latest` tag is supported but resolves to a specific version at install time and is recorded as the exact version in the lockfile.

Post-v1 will add `blackbeard repo install crews/research-crew@1.0.0 --resolve-deps` with semver range resolution, conflict detection, and lockfile generation.

## 8. Governance

- **RBAC**: Repository assets are governed by the same RBAC system (PRD 03). Publishing requires `create` on the asset kind in the repository namespace.
- **Audit**: Every publish, install, and version change is audit-logged.
- **Deprecation**: Assets can be marked deprecated with a migration message.
- **Deletion**: Only org admins can delete published assets. Deletion checks for active dependents.

## 9. Acceptance Criteria

1. An agent can be published to the repository with semver versioning.
2. A WASM tool can be published with its `.wasm` binary and WIT interface.
3. Published assets are discoverable via UI search and browsable by category.
4. `ref: repo:agents/name@version` resolves correctly at load time.
5. Version pinning (`@1.2.0`) and range (`@1.x`) work correctly.
6. Overrides at point of use work (change goal, add tools, etc.).
7. Approval workflow blocks publication until admin approves (when configured).
8. Breaking change detection warns when a new major version has active dependents.
