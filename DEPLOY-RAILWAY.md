# Deploying DotCome CRM to Railway

You'll get `https://your-project.up.railway.app` — multi-user, always on, with persistent data on a Railway Volume so your `crm.db` survives every redeploy.

> **Why this works for 3 users:** SQLite in WAL mode (already configured in `app.py`) handles concurrent reads with no blocking and serializes writes at sub-millisecond granularity. With `synchronous=FULL` it's crash-safe. Plenty for a 3-person team — but the database file **must** live on a Railway Volume, not the ephemeral container filesystem.

---

## Prerequisites

- A Railway account: https://railway.app (free tier is enough to start; paid for always-on).
- The Railway CLI (recommended) — install from https://docs.railway.app/develop/cli, or skip and use the dashboard.
- Your project folder, including `crm.db` (it gets bundled and copied into the volume on first boot).

---

## 1. Push the project to GitHub (recommended) or use the CLI

**Option A — GitHub (easier for redeploys):**
```bash
cd "DotCome CRM"
git init
git add .
git commit -m "DotCome CRM"
# create a GitHub repo, then:
git remote add origin git@github.com:YOU/dotcome-crm.git
git push -u origin main
```

**Option B — direct upload via CLI:**
```bash
railway login
railway init           # creates a new project
railway up             # uploads the folder and builds
```

---

## 2. Create the service on Railway

1. **Dashboard → New Project → Deploy from GitHub repo** (Option A) and select the repo. Railway's Nixpacks auto-detects Python and uses the `Procfile` you already have.
2. After the first build finishes, the service is running but **not yet usable** — you still need a volume + env vars.

---

## 3. Add a Volume for the database (critical)

Without this, **every redeploy wipes your data.**

1. In the service, open **Settings → Volumes → + New Volume**.
2. **Mount path**: `/data`
3. **Size**: 1 GB is plenty (the current DB is ~4 MB).
4. Save.

When the service restarts with the volume attached, the app's startup code in `app.py` (`seed_db_from_bundle`) will copy your bundled `crm.db` into `/data/crm.db` automatically — but only the first time, when the volume is empty. Subsequent deploys leave the volume's data alone.

---

## 4. Set environment variables

In the service → **Variables**, add:

| Variable | Value | Notes |
|---|---|---|
| `CRM_DB_PATH` | `/data/crm.db` | Points the app at the volume |
| `CRM_SECRET_KEY` | (run the command below) | Stable — don't regenerate, it logs everyone out |
| `CRM_SECURE_COOKIES` | `1` | Forces session cookies to HTTPS-only |

Generate the secret key locally:
```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

After saving variables, Railway redeploys automatically.

---

## 5. Generate a public URL

Service → **Settings → Networking → Generate Domain**. You'll get `https://your-project.up.railway.app`. Open it, log in as `liam` / `bar` / `rom`, and you should see your 6,081 leads with the owner badges.

---

## 6. Keep replicas at 1 (do not horizontally scale)

SQLite cannot run safely across multiple containers — concurrent writes from two replicas to the same volume **will corrupt the database.** Railway's default is 1 replica. If you ever see "Replicas" in service settings, leave it at **1**. (For more horsepower, raise the plan tier to upgrade CPU/RAM rather than adding replicas.)

---

## 7. Backups (do this — the volume is not auto-backed-up)

Railway Volumes are durable but **not snapshotted automatically**. For real customer data, set up at least one of:

### Option A — manual SQLite dump (simplest, do it weekly)
```bash
railway run --service=dotcome-crm bash -c "sqlite3 /data/crm.db .dump > /tmp/crm-$(date +%F).sql"
railway run --service=dotcome-crm cat /tmp/crm-$(date +%F).sql > backup-$(date +%F).sql
```
Save the file somewhere off-Railway (Drive, S3, your laptop).

### Option B — Litestream (continuous streaming to S3) — recommended
[Litestream](https://litestream.io) replicates SQLite to S3/B2/etc in real time and can restore on container start. Add to your `Procfile`:
```
web: litestream replicate -exec "gunicorn wsgi:application --workers 1 --threads 8 --bind 0.0.0.0:$PORT --timeout 60"
```
plus a `litestream.yml` pointing at your S3 bucket. This gives you point-in-time recovery and survives a Railway volume failure.

### Option C — daily cron via Railway scheduled job
Create a second service from the same repo with a Cron schedule that runs `python -c "import shutil, datetime; shutil.copy('/data/crm.db', f'/data/backups/crm-{datetime.date.today()}.db')"` and prunes old files.

For a 3-person CRM, **Option A weekly + Option C daily on the same volume** is the practical baseline. **Option B** is the gold standard.

---

## 8. Updating later

With GitHub: `git push` → Railway redeploys automatically.

With CLI: `railway up` from the project folder.

The volume's `/data/crm.db` is preserved across all redeploys. The app's `ensure_schema()` migration is idempotent — adding columns or tables in future versions will run automatically without touching existing data.

---

## Sanity checklist before going live

- [ ] Volume mounted at `/data`, size ≥ 1 GB
- [ ] `CRM_DB_PATH=/data/crm.db`
- [ ] `CRM_SECRET_KEY` set to a stable random hex (not regenerated each deploy)
- [ ] `CRM_SECURE_COOKIES=1`
- [ ] Replicas = 1 (default)
- [ ] Public domain generated, you can log in
- [ ] You see all 6,081 leads with owner badges
- [ ] Backup strategy in place (Option A, B, or C above)

---

## Troubleshooting

- **"No such table: leads"** → volume seeding didn't fire (the bundled `crm.db` wasn't shipped). Check Deploy logs; ensure `crm.db` isn't in `.gitignore` / `.railwayignore`.
- **Login loop / session doesn't stick** → `CRM_SECRET_KEY` is missing or being regenerated each deploy. Set it explicitly in Variables.
- **Cookie not set on Railway domain** → `CRM_SECURE_COOKIES=1` requires HTTPS. Railway domains are HTTPS by default; if you're on a custom domain, make sure cert is provisioned.
- **Data lost after redeploy** → the volume isn't mounted, or `CRM_DB_PATH` doesn't match the mount path. Confirm both in Settings.
- **Deploy fails on `gunicorn: not found`** → confirm `gunicorn>=21.2` is in `requirements.txt` and Railway rebuilt after the change.
