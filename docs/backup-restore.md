# Backup and Restore

Strategies for backing up and restoring Blackbeard data.

## What to Back Up

| Component | Contains | Method |
|-----------|----------|--------|
| PostgreSQL | Resources, executions, users, audit logs, resource versions | pg_dump |
| Resource YAML | Resource definitions | CLI export or API export |
| `.env` / secrets | API keys, JWT secret, DB passwords | Manual copy |
| LiteLLM config | Model routing rules | Synced from LLMConnection resources |

Valkey does not need backup. It stores ephemeral data (collaboration sessions, health check state) that rebuilds on restart.

## PostgreSQL Backup

### Docker Compose

```bash
# Full database dump (compressed)
docker compose exec postgres pg_dump -U blackbeard blackbeard \
  | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz

# Restore from dump
gunzip -c backup-20240101-120000.sql.gz \
  | docker compose exec -T postgres psql -U blackbeard blackbeard
```

### Kubernetes (Helm)

```bash
# Get the pod name
PG_POD=$(kubectl get pods -l app=blackbeard-postgres -o jsonpath='{.items[0].metadata.name}')

# Dump
kubectl exec $PG_POD -- pg_dump -U blackbeard blackbeard \
  | gzip > backup-$(date +%Y%m%d-%H%M%S).sql.gz

# Restore
gunzip -c backup.sql.gz \
  | kubectl exec -i $PG_POD -- psql -U blackbeard blackbeard
```

### Automated Backups (cron)

```bash
# Add to crontab: daily backup at 2am, keep 30 days
0 2 * * * docker compose -f /path/to/docker-compose.yaml exec -T postgres \
  pg_dump -U blackbeard blackbeard | gzip > /backups/blackbeard-$(date +\%Y\%m\%d).sql.gz \
  && find /backups -name 'blackbeard-*.sql.gz' -mtime +30 -delete
```

## Resource YAML Export

Export all resources as YAML for version control or migration between instances.

### CLI

```bash
# Export all resources to a single file
uv run blackbeard export --all > resources-backup.yaml

# Export all resources to a directory (one file per resource)
uv run blackbeard export --all -o backup/

# Export specific kinds
uv run blackbeard export Agent > agents.yaml
uv run blackbeard export Crew > crews.yaml
```

### API

```bash
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/resources/export > resources-backup.yaml
```

### Restore from YAML

```bash
# Apply all resources from a file
uv run blackbeard apply -f resources-backup.yaml

# Apply from a directory
uv run blackbeard apply -f backup/

# Dry run first
uv run blackbeard apply -f resources-backup.yaml --dry-run
```

## Secrets Backup

Back up these files manually (never commit to git):

- `.env` (API keys, JWT secret, database credentials)
- `.admin-credentials` (generated admin password)
- Any TLS certificates

Store encrypted backups in a secure location (cloud KMS, Vault, etc.).

## Full Disaster Recovery

1. **Provision infrastructure** (Docker Compose or Kubernetes)
2. **Restore `.env`** with secrets
3. **Start services** (`./run.sh` or `helm install`)
4. **Restore PostgreSQL** from pg_dump
5. **Seed RBAC** if needed (`bash deploy/seed.sh`)
6. **Verify health** (`curl http://localhost:8000/api/v1/health`)
7. **Verify resources** (`uv run blackbeard list Agent`)

LiteLLM model configurations will rebuild automatically from LLMConnection resources on next API startup (dynamic sync).

## Migration Between Instances

To move from one Blackbeard instance to another:

```bash
# On source instance
uv run blackbeard export --all > migration.yaml

# On target instance
uv run blackbeard apply -f migration.yaml
```

This exports and imports all resource definitions. Execution history, audit logs, and user accounts require a PostgreSQL dump/restore.

## Version Rollback

Individual resources can be rolled back to any previous version without a full restore:

```bash
# List versions
curl -H "X-API-Key: $KEY" \
  http://localhost:8000/api/v1/agents/researcher/versions

# Rollback to version 3
curl -X POST -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d '{"version": 3}' \
  http://localhost:8000/api/v1/agents/researcher/rollback
```
