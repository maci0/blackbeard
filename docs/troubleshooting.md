# Troubleshooting Guide

Common issues and fixes for Blackbeard operators.

---

## Startup Issues

### API container fails to start

**Symptom:** `api` container exits immediately or restarts repeatedly.

**Check logs:**
```bash
docker compose logs api
```

**Common causes:**
- **Database not ready:** The API waits for PostgreSQL. If PG takes longer than the health check start period (120s), the API may fail. Increase `start_period` in docker-compose.yaml.
- **Missing environment variables:** Check `.env` has `DATABASE_URL`, `JWT_SECRET`, `BLACKBEARD_API_KEY`.
- **Port conflict:** Another process on port 8000. Run `lsof -i :8000` to check.

### UI shows "API Unavailable"

**Symptom:** Frontend renders but shows "Cannot connect to the Blackbeard API" with a spinner.

**Causes:**
- API container not running or unhealthy
- Nginx proxy misconfigured (check `API_UPSTREAM` env var in UI container)
- Network issue between UI and API containers

**Fix:**
```bash
# Check API health directly
curl http://localhost:8000/api/v1/health

# Check container status
docker compose ps

# Restart API
docker compose restart api
```

### LiteLLM proxy fails to start

**Symptom:** LiteLLM container exits with OOM or config errors.

**Causes:**
- Insufficient memory (LiteLLM needs at least 512MB)
- Invalid `litellm_config.yaml`
- Missing `LITELLM_MASTER_KEY`

**Fix:**
```bash
# Check LiteLLM logs
docker compose logs litellm

# Verify config
docker compose exec litellm cat /app/config.yaml

# Increase memory limit in docker-compose.yaml
```

---

## Authentication Issues

### "Invalid credentials" on login

- Verify email and password match what was created during `seed.sh` or registration
- Check `.admin-credentials` for the auto-generated admin password
- Verify JWT_SECRET hasn't changed since user creation (changing it invalidates all tokens)

### API key not working

- Verify key matches `BLACKBEARD_API_KEY` in `.env`
- Check header format: `X-API-Key: your-key` (not `Authorization: Bearer`)
- API key auth uses constant-time comparison, so timing attacks won't help diagnose

### JWT token expired

- Access tokens expire after 15 minutes
- Refresh tokens expire after 7 days
- The frontend auto-refreshes tokens; the CLI stores credentials in `~/.config/blackbeard/`
- Force re-login: `uv run blackbeard login`

---

## Execution Issues

### Crew execution hangs

**Symptom:** Execution stays in "running" status indefinitely.

**Causes:**
- LLM provider unreachable (check LiteLLM logs)
- Task with `human_input: true` waiting for HITL response
- Budget exceeded (LiteLLM blocks the request)

**Diagnose:**
```bash
# Check execution events
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/executions/<id>/events

# Check LiteLLM logs for blocked requests
docker compose logs litellm | grep -i "budget\|error\|blocked"

# Cancel a stuck execution
curl -X POST -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/executions/<id>/cancel
```

### "Budget exceeded" error

- Check AgentPolicy `max_usd` and `max_tokens` values
- LiteLLM enforces budgets via virtual keys created per-execution
- The most restrictive policy across all agents in the crew wins
- View spend: `curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/executions/<id>/spend`

### CrewAI delegation errors

- Check agent `allow_delegation` flag in the spec
- Verify AgentPolicy `allow_delegation` is not set to false
- Check that the target agent exists and is referenced in the crew

---

## Resource Issues

### "Resource validation failed"

- Check the spec against the JSON schema for that kind
- Common mistakes: wrong field types, extra properties, missing required fields
- Validate offline: `uv run blackbeard validate -f resource.yaml`
- Schema definitions: `backend/blackbeard/resources/spec_schemas.py`

### "Resource already exists" on import

- Both the CLI `apply` command and the API `POST` endpoint upsert: a `POST` to an existing kind/name/project updates it and returns `200` instead of `201`
- `PUT` requires the current `version` field (optimistic locking) and returns `409` on mismatch

### Broken resource references

- Refs use format `ref:kind-plural/name` (e.g., `ref:agents/researcher`)
- The referenced resource must exist before the referencing resource is used
- `apply -f directory/` resolves dependencies in order
- Refs are extracted and tracked on create/update; missing targets surface at crew build time as loader errors

---

## Database Issues

### PostgreSQL connection refused

```bash
# Check if PG is running
docker compose ps postgres

# Check PG logs
docker compose logs postgres

# Test connectivity
docker compose exec postgres pg_isready -U blackbeard
```

### Schema migration errors

- Blackbeard uses `create_all` for initial tables and Alembic for migrations
- If Alembic fails, check `backend/alembic/versions/` for migration files
- Manual reset (destroys data): `docker compose down -v && ./run.sh`

### Slow queries

- Check if indexes exist: `docker compose exec postgres psql -U blackbeard -c "\di"`
- Common slow queries: unfiltered resource lists, audit log scans
- Add `?limit=50` to API list endpoints to paginate

---

## Frontend Issues

### Page shows blank white screen

- Open browser dev tools (F12), check Console tab for errors
- Common cause: JavaScript bundle failed to load
- Clear browser cache and reload
- Check that the Vite dev server (`:3000`) or Nginx is serving files

### Studio canvas empty after loading crew

- Check that the crew resource has valid agent and task refs
- Open browser console for React Flow errors
- Try auto-layout button to reset node positions
- Check localStorage for corrupted studio state: `localStorage.removeItem('blackbeard_studio_state')`

### Dark mode not applying

- Toggle via the sun/moon button in the sidebar footer
- The setting cycles through light, dark, and system
- Check that no browser extension is overriding colors
- Verify the `dark` class is present on `<html>` element

---

## CLI Issues

### "Connection refused" errors

```bash
# Check server is reachable
uv run blackbeard health

# Specify server explicitly
uv run blackbeard --server http://localhost:8000 health

# Check stored config
cat ~/.config/blackbeard/credentials.json
```

### "Unknown kind" errors

- Verify the kind name is capitalized correctly (e.g., `Agent`, not `agent`)
- Check `uv run blackbeard --help` for valid kinds
- The CLI uses the same kind registry as the backend

---

## Valkey / Redis Issues

### Collaboration not working

- Verify Valkey is running: `docker compose ps valkey`
- Check Valkey connectivity: `docker compose exec valkey redis-cli ping`
- Collaboration uses WebSocket + Valkey pub/sub for multi-replica fan-out
- Single replica: works without Valkey (falls back to local broadcast)

---

## Performance Issues

### High API latency

- Run load tests: `locust -f tests/load/locustfile.py --host http://localhost:8000`
- Check database query times in API logs (look for slow query warnings)
- Check LiteLLM proxy latency: `curl -o /dev/null -w '%{time_total}' http://localhost:4000/health`
- Consider adding PostgreSQL connection pooling (PgBouncer) for high concurrency

### High memory usage

- LiteLLM is the heaviest service (500MB+)
- API memory grows with concurrent executions (each gets a thread + event loop)
- Set `max_concurrent` on Automations to limit parallel executions
- Monitor with `docker stats`

---

## Getting Help

1. Check API logs: `docker compose logs api -f`
2. Check health: `curl http://localhost:8000/api/v1/health`
3. Check readiness: `curl http://localhost:8000/api/v1/health/ready`
4. Enable debug mode: set `DEBUG=true` in `.env` for Swagger UI at `/docs`
5. Check audit logs: `curl -H "X-API-Key: $KEY" http://localhost:8000/api/v1/audit-logs`
