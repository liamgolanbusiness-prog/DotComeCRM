# Deploying DotCome CRM to PythonAnywhere

You'll have a live CRM at `https://YOURUSER.pythonanywhere.com` that works from your phone, tablet, or anywhere — even when your PC is off.

## 1. Create the account

1. Go to https://www.pythonanywhere.com/pricing/ and click **Create a Beginner account** (free).
2. Pick a username — this becomes your URL (`https://liamg.pythonanywhere.com` or similar).

## 2. Upload the project files

You have two options. **Zip upload is simplest.**

### Option A — Zip upload
1. Zip the whole project folder (on your PC):
   `app.py`, `wsgi.py`, `init_db.py`, `requirements.txt`, `crm.db`, `leads.xlsx`, `templates/`, `static/`
2. In PythonAnywhere, open the **Files** tab → upload the zip to `/home/YOURUSER/`.
3. Open a **Bash console** (from the Consoles tab) and run:
   ```
   cd ~
   unzip dotcome-crm.zip -d dotcome-crm
   cd dotcome-crm
   ls
   ```
   You should see `app.py`, `crm.db`, etc.

### Option B — Git
If the project is in a git repo, `git clone` it in a Bash console into `~/dotcome-crm`.

## 3. Install dependencies

In the Bash console (from the project folder):
```
pip3.10 install --user -r requirements.txt
```
(Use whichever Python version matches what you pick in step 4. `pip3.10` / `pip3.11` etc.)

## 4. Create the web app

1. Go to the **Web** tab → **Add a new web app**.
2. Choose **Manual configuration** (not Flask — we're using the WSGI file directly).
3. Pick **Python 3.10** (or 3.11).
4. Under **Code**:
   - **Source code**: `/home/YOURUSER/dotcome-crm`
   - **Working directory**: `/home/YOURUSER/dotcome-crm`

## 5. Configure the WSGI file

1. On the Web tab click the **WSGI configuration file** link (it's something like `/var/www/YOURUSER_pythonanywhere_com_wsgi.py`).
2. Replace its contents with:

```python
import os, sys

PROJECT_DIR = "/home/YOURUSER/dotcome-crm"        # <-- your username

# Secrets — set these, do NOT commit them to git
os.environ["CRM_PASSWORD"]   = "PICK-A-STRONG-PASSWORD"
os.environ["CRM_SECRET_KEY"] = "PASTE-A-LONG-RANDOM-HEX-HERE"
os.environ["CRM_DB_PATH"]    = os.path.join(PROJECT_DIR, "crm.db")

if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from app import app as application
```

Generate a secret key in a Bash console:
```
python3 -c "import secrets; print(secrets.token_hex(32))"
```
Paste that hex string as `CRM_SECRET_KEY`.

## 6. (Optional but recommended) Static files mapping

On the Web tab, under **Static files**, add:
| URL | Directory |
|---|---|
| `/static/` | `/home/YOURUSER/dotcome-crm/static` |

This makes CSS/JS load faster (served directly by nginx instead of Flask).

## 7. Reload and open

1. Click the big green **Reload** button at the top of the Web tab.
2. Open `https://YOURUSER.pythonanywhere.com/` in your browser.
3. Log in with the password you set. You should see your 6,081 leads (plus any edits you'd already made — `crm.db` came along in the upload).

## Updating later

When you make changes locally and want to push them live:
1. Re-upload the changed files (or `git pull` in the Bash console).
2. Click **Reload** on the Web tab.

## Backing up

The database is at `/home/YOURUSER/dotcome-crm/crm.db`. Download it from the **Files** tab any time. You can also copy it somewhere safe with:
```
cp crm.db backups/crm-$(date +%F).db
```

## Troubleshooting

- **"Something went wrong :-("** → click the Web tab's **Error log** link. Usually a typo in the WSGI file path or a missing env var.
- **Login loop / session doesn't stick** → make sure `CRM_SECRET_KEY` is set and stable (not re-generated on every restart).
- **"No such file or directory: crm.db"** → the file wasn't uploaded, or `CRM_DB_PATH` points to the wrong place.
- **Free plan limitation**: PythonAnywhere's free tier only allows outbound HTTP to a whitelist. Your CRM doesn't make outbound calls, so this doesn't matter. (WhatsApp is a redirect from the user's browser, not from the server.)

## Security notes

- The login cookie is 30 days. Use the ⏻ button in the top-right to log out.
- Anyone with the URL + password can read/edit all leads — keep the password strong.
- `crm.db` is public-filesystem on PythonAnywhere (no one else can see your home dir on the free plan, but treat it as sensitive).
- If you ever rotate `CRM_SECRET_KEY`, all existing logins are invalidated (everyone has to log in again).
