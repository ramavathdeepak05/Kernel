# ALIS Database Restore Runbook

**Classification:** Operations
**Owner:** Platform Team (QUAICU Pvt. Ltd.)
**RTO Target:** < 4 hours | **RPO Target:** < 24 hours

---

## When to use this runbook

- Accidental data deletion (table or row level)
- Corrupted database
- Disaster recovery (server loss, storage failure)
- Migration rollback required

---

## Step 1 — Identify the backup to restore

```bash
# List available backups in MinIO
mc ls alisminio/alis-backups/daily/ | sort -r | head -20

# Or list local backups
ls -lh /var/backups/alis/daily/ | sort -r | head -20
```

Note the filename of the target backup (e.g. `alis_20260319_030000.dump`).

---

## Step 2 — Download from MinIO (if restoring from cloud)

```bash
mc cp alisminio/alis-backups/daily/alis_20260319_030000.dump /tmp/restore.dump
```

---

## Step 3 — Stop application traffic

```bash
# Scale down app containers (preserve DB)
docker-compose stop app celery celery-beat nginx

# Verify no active connections (optional)
psql -U postgres -c "SELECT count(*) FROM pg_stat_activity WHERE datname = 'alis';"
```

---

## Step 4 — Drop and recreate database

```bash
psql -U postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'alis';"
psql -U postgres -c "DROP DATABASE IF EXISTS alis;"
psql -U postgres -c "CREATE DATABASE alis OWNER postgres;"
```

---

## Step 5 — Restore from backup

```bash
export PGPASSWORD="${POSTGRES_PASSWORD}"
pg_restore \
  --host=localhost \
  --port=5432 \
  --username=postgres \
  --dbname=alis \
  --no-owner \
  --no-acl \
  --verbose \
  /tmp/restore.dump
```

Expected: restore prints table names as it restores. Errors about sequences or extension ownership are warnings, not failures.

---

## Step 6 — Verify restore

```bash
psql -U postgres -d alis -c "SELECT COUNT(*) FROM organizations;"
psql -U postgres -d alis -c "SELECT COUNT(*) FROM users;"
psql -U postgres -d alis -c "SELECT COUNT(*) FROM students;"
psql -U postgres -d alis -c "SELECT MAX(created_at) FROM domain_events;"
```

Confirm row counts are plausible and the last domain event timestamp matches expectations.

---

## Step 7 — Re-enable RLS policies

```bash
psql -U postgres -d alis -f ALIS/migrations/rls_policies.sql
```

(RLS policies are included in the restore from pg_dump, but re-running is safe — all use `CREATE POLICY IF NOT EXISTS`.)

---

## Step 8 — Restart application

```bash
docker-compose up -d app celery celery-beat nginx
```

Watch logs for 60 seconds:
```bash
docker-compose logs -f app | head -100
```

---

## Step 9 — Validate health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
```

Both must return `{"status": "ok"}`.

---

## Step 10 — Notify stakeholders

- Send incident update via WhatsApp / email
- Update status page
- File incident report in Linear project `ALIS-INFRA`

---

## Point-in-time recovery (partial data loss)

For row-level recovery without full restore:

```bash
# Restore to a separate DB
createdb alis_restore
pg_restore --dbname=alis_restore /tmp/restore.dump

# Extract specific rows
psql -d alis_restore -c "COPY (SELECT * FROM students WHERE ...) TO '/tmp/recovered.csv' CSV HEADER;"

# Import to production
psql -d alis -c "\copy students FROM '/tmp/recovered.csv' CSV HEADER ON CONFLICT DO NOTHING;"
```

---

*Runbook v1.0 | March 2026 | QUAICU Pvt. Ltd.*
