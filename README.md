# DotCome CRM

Local CRM built around `leads.xlsx` (6,081 leads). Flask + SQLite + vanilla JS, RTL Hebrew UI.

## First run
```
pip install -r requirements.txt
python init_db.py     # imports leads.xlsx -> crm.db (safe to re-run)
python app.py         # http://127.0.0.1:5000
```
Or just double-click `run.bat` (opens browser + starts server).

## Files
- `leads.xlsx` — original source (untouched, treat as backup)
- `crm.db` — SQLite, **all your CRM updates live here**
- `init_db.py` — one-shot importer (only inserts new `place_id`s, never overwrites)
- `app.py` — Flask backend + WhatsApp templates
- `templates/index.html`, `static/` — frontend

## Workflow → status mapping
| Stage | Status |
|---|---|
| Cold-call list | `new` → `no_answer` / `interested` / `not_interested` |
| Building demo | `demo_built` |
| Sent demo | `demo_sent` → `followup` |
| Offer made | `offer_made` |
| 50% paid | `half_paid` |
| Waiting on assets | `collecting_assets` |
| Final build | `finalizing` |
| Live, awaiting full payment | `published` |
| Done | `done` |

## Quick actions
- **Click a lead** → detail panel on the left
- **📞 התקשר** → `tel:` link, also stamps `last_contacted`
- **💬 WhatsApp** → opens `wa.me/972...` in a new tab with a templated message for the current stage. **No need to save the contact.** Edit the message before sending.
- **שמור שינויים** → saves status, notes, follow-up date, demo/final URLs, prices

## Editing WhatsApp templates
Edit the `TEMPLATES` dict in `app.py`. Placeholders: `{name}`, `{demo}`, `{final}`. Restart Flask after editing.

## Phone normalization
Israeli formats like `077-804-0610`, `054-808-2300` are auto-converted to `972778040610` for the wa.me link. If the lead has no phone, the WhatsApp button shows `(אין מספר טלפון)`.

## Adding new leads later
Drop them into `leads.xlsx` (same columns) and re-run `python init_db.py`. Existing leads are skipped by `place_id`, so your CRM data is preserved.

## Backup
The whole CRM state is in `crm.db`. Copy it anywhere to back up.
