# PRD 13 — CLI Parity

## 1. Purpose

Ensure every operation available in the Blackbeard UI can also be performed via the CLI (`blackbeard` command). The visual graph editor (Studio) is inherently graphical, but all CRUD, auth, execution, and RBAC operations must have CLI equivalents for scripting, CI/CD, and headless environments.

---

## 1.1 MVP Scope

**Implemented:** ✅ Fully implemented as a standalone package (`cli/`) with 28 commands (including 4 groups with subcommands) spanning all three phases. All CLI commands listed in this PRD are shipped and functional. CLI modules: `cli/blackbeard_cli/__main__.py`, `cli/blackbeard_cli/auth_cmds.py`, `cli/blackbeard_cli/credentials.py`, `cli/blackbeard_cli/users.py`, `cli/blackbeard_cli/rbac.py`, `cli/blackbeard_cli/exec.py`, `cli/blackbeard_cli/export_cmd.py`, `cli/blackbeard_cli/helpers.py`. Commands include: `apply`, `validate`, `get`, `list`, `delete`, `kickoff`, `train`, `test-crew`, `status`, `pull`, `cancel`, `executions`, `events --follow`, `export`, `login`/`logout`/`whoami`/`register`, `user list/invite`, `group list/create/delete/add-member/remove-member/members`, `role list/describe`, `rolebinding list/create`, `apikey generate/rotate/show`, `health`. JWT credential storage in `~/.config/blackbeard/` with auto-refresh. Both Rich (human) and JSON (machine) output modes.

**Implemented (post-MVP):** Interactive TUI shell via `blackbeard shell` command using prompt_toolkit, with context-aware autocomplete, persistent history, rich output, and built-in commands (help, use, ls, get, cat, run, watch, status, executions, health).

**Deferred to post-MVP:** Plugin system for custom commands, `blackbeard tool compile`, `blackbeard repo publish/install`, `blackbeard deploy/rollback`.

---

## 2. Gap Analysis

### 2.1 What CLI Already Has

| Command | Description |
|---------|-------------|
| `blackbeard health [--ready]` | Liveness and readiness checks |
| `blackbeard validate -f <path>` | Offline YAML validation |
| `blackbeard apply -f <path>` | Create/update resources from YAML |
| `blackbeard get <Kind> <name>` | Get a single resource |
| `blackbeard list <Kind>` | List resources (with label filter) |
| `blackbeard delete <Kind> <name>` | Delete a resource |
| `blackbeard kickoff <crew>` | Run a crew (with --wait, --input) |
| `blackbeard status <id>` | Execution status (with --watch) |

### 2.2 What's Missing

| UI Feature | Proposed CLI Command | Priority |
|------------|---------------------|----------|
| Login (email/password) | `blackbeard login` | P0 |
| View current user | `blackbeard whoami` | P0 |
| Logout (clear token) | `blackbeard logout` | P0 |
| Register account | `blackbeard register` | P1 |
| List users | `blackbeard user list` | P1 |
| Invite user | `blackbeard user invite` | P1 |
| Deactivate user | `blackbeard user deactivate <email>` | P2 |
| List groups | `blackbeard group list` | P2 |
| Create group | `blackbeard group create <name>` | P2 |
| Add user to group | `blackbeard group add-member <group> <email>` | P2 |
| List roles | `blackbeard role list` | P1 |
| Get role details | `blackbeard role get <name>` | P1 |
| Create role from YAML | Already works via `blackbeard apply` | — |
| Delete role | Already works via `blackbeard delete Role <name>` | — |
| List role bindings | `blackbeard rolebinding list` | P1 |
| Create role binding | `blackbeard rolebinding create` | P1 |
| List executions | `blackbeard executions` | P0 |
| Execution events (stream) | `blackbeard events <id> [--follow]` | P1 |
| Cancel execution | `blackbeard cancel <id>` | P1 |
| Generate API key | `blackbeard apikey generate` | P1 |
| Rotate API key | `blackbeard apikey rotate` | P2 |
| Export resource as YAML | `blackbeard export <Kind> <name>` | P1 |
| Export all resources | `blackbeard export --all` | P1 |

---

## 3. Command Design

### 3.1 Authentication Commands

```
blackbeard login [--email <email>] [--password <password>]
```
Interactive by default (prompts for email/password). Stores JWT in `~/.config/blackbeard/credentials.json` (XDG-compliant). Subsequent commands use the stored token automatically, falling back to `--api-key` / `BLACKBEARD_API_KEY`.

```
blackbeard whoami [--json]
```
Shows current identity: email, display name, role, token expiry. Uses stored JWT or API key.

```
blackbeard logout
```
Removes stored credentials from `~/.config/blackbeard/credentials.json`.

```
blackbeard register --email <email> --password <password> --name <name>
```
Creates a new account. Non-interactive (all args required).

### 3.2 User & Group Commands

```
blackbeard user list [--json]
blackbeard user invite --email <email> --password <password> --name <name> [--role <role>]
blackbeard user deactivate <email> [-y]
blackbeard user activate <email>

blackbeard group list [--json]
blackbeard group create <name> [--description <desc>]
blackbeard group delete <name> [-y]
blackbeard group add-member <group> <email>
blackbeard group remove-member <group> <email>
blackbeard group members <group> [--json]
```

### 3.3 RBAC Commands

```
blackbeard role list [--json]
blackbeard role get <name> [--json]
blackbeard role describe <name>                # human-readable rule matrix

blackbeard rolebinding list [--json]
blackbeard rolebinding create --role <role> --subject <kind>/<name> [--namespace <ns>]
blackbeard rolebinding delete <name> [-y]
```

### 3.4 Execution Commands

```
blackbeard executions [--status <status>] [--crew <name>] [--limit N] [--json]
blackbeard events <execution-id> [--follow] [--json]
blackbeard cancel <execution-id> [-y]
```

### 3.5 Export Commands

```
blackbeard export <Kind> <name> [-o <file>]    # single resource as YAML
blackbeard export --all [-o <dir>]             # all resources, one file per kind
blackbeard export --all --single-file          # all resources in one multi-doc YAML
```

### 3.6 API Key Management

```
blackbeard apikey generate [--json]            # generate personal API key
blackbeard apikey rotate [-y] [--json]         # revoke old, generate new
blackbeard apikey show [--json]                # show current key (masked)
```

---

## 4. Credential Storage

JWT tokens stored in `~/.config/blackbeard/credentials.json`:

```json
{
  "server": "http://localhost:8000",
  "access_token": "eyJ...",
  "refresh_token": "eyJ...",
  "email": "admin@blackbeard.sh",
  "expires_at": "2026-05-18T12:00:00Z"
}
```

File permissions: `0600` (owner read/write only).

CLI auto-refreshes expired access tokens using the refresh token. If both expired, prompts for re-login.

Auth resolution order:
1. `--api-key` flag / `BLACKBEARD_API_KEY` env (highest priority)
2. Stored JWT from `~/.config/blackbeard/credentials.json`
3. Prompt for login (interactive only)

---

## 5. Output Modes

All commands support:
- **Human mode** (default): Rich tables, panels, colors
- **JSON mode** (`--json`): Machine-readable output to stdout, errors/progress to stderr
- **Quiet mode** (`-q`): Minimal output (exit code only)

---

## 6. Implementation Phases

### Phase 1 (P0) — Core Gaps
1. `blackbeard login` / `logout` / `whoami`
2. `blackbeard executions` (list all)
3. Credential storage with auto-refresh

### Phase 2 (P1) — RBAC & Export
4. `blackbeard user list/invite`
5. `blackbeard role list/get/describe`
6. `blackbeard rolebinding list/create/delete`
7. `blackbeard events <id> [--follow]`
8. `blackbeard cancel <id>`
9. `blackbeard export`
10. `blackbeard register`
11. `blackbeard apikey generate/rotate/show`

### Phase 3 (P2) — Full Parity
12. `blackbeard user deactivate/activate`
13. `blackbeard group` commands
14. `blackbeard apikey rotate`

---

## 7. Verification

1. Every UI operation has a CLI equivalent (excluding visual graph editor)
2. `blackbeard login && blackbeard whoami` works end-to-end
3. `blackbeard executions --json | jq` produces valid JSON
4. `blackbeard export --all | blackbeard apply -f -` round-trips
5. Credential file has 0600 permissions
6. Auto-refresh works when access token expires
7. All commands have `--help`, `--json`, and useful error messages
