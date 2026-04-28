"""
WSGI entry point for PythonAnywhere (or any WSGI host).

On PythonAnywhere:
1. Edit the web-app's WSGI config file (Web tab -> "WSGI configuration file").
2. Replace its contents with something like:

    import os, sys

    # ---- CHANGE THESE to your PythonAnywhere username / project path ----
    PROJECT_DIR = "/home/YOURUSER/dotcome-crm"

    # Secrets (don't commit these to git!)
    os.environ["CRM_PASSWORD"]   = "pick-a-strong-password"
    os.environ["CRM_SECRET_KEY"] = "a-long-random-hex-string"
    os.environ["CRM_DB_PATH"]    = os.path.join(PROJECT_DIR, "crm.db")

    if PROJECT_DIR not in sys.path:
        sys.path.insert(0, PROJECT_DIR)

    from app import app as application

3. Click "Reload" on the Web tab.

For local dev you can keep using `python app.py`.
"""
from app import app as application

if __name__ == "__main__":
    application.run()
