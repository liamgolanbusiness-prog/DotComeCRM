"""DotCome CRM - Flask app over crm.db."""
import os, sqlite3, re, urllib.parse, secrets, random, json, shutil
from functools import wraps
from flask import Flask, jsonify, request, render_template, abort, session, redirect, url_for

# --- Config (env vars, with safe dev defaults) -----------------------------
DB            = os.environ.get("CRM_DB_PATH", "crm.db")
SECRET_KEY    = os.environ.get("CRM_SECRET_KEY") or secrets.token_hex(32)
SECURE_COOKIE = os.environ.get("CRM_SECURE_COOKIES", "0") == "1"

USERS = {
    "liam": "Liami123!",
    "bar":  "Avnon123",
    "ely":  "Ely123!",
}

# First-boot seeding: when CRM_DB_PATH points at a mounted volume that's empty
# (e.g. fresh Railway deploy), copy the bundled crm.db into it once so we don't
# start with an empty database.
def seed_db_from_bundle():
    target = os.path.abspath(DB)
    if os.path.exists(target):
        return
    bundled = os.path.abspath(os.path.join(os.path.dirname(__file__), "crm.db"))
    if bundled == target or not os.path.exists(bundled):
        return
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    shutil.copy2(bundled, target)

seed_db_from_bundle()

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"]   = SECURE_COOKIE
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 days

def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get("auth"):
            if request.path.startswith("/api/"):
                return jsonify({"error": "unauthorized"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*a, **kw)
    return wrapper

STATUSES = [
    ("new",              "חדש"),
    ("no_answer",        "לא ענה"),
    ("interested",       "מעוניין"),
    ("demo_built",       "דמו מוכן"),
    ("demo_sent",        "דמו נשלח"),
    ("followup",         "במעקב"),
    ("offer_made",       "הצעה נמסרה"),
    ("half_paid",        "שולם 50%"),
    ("collecting_assets","אוסף חומרים"),
    ("finalizing",       "בבנייה סופית"),
    ("published",        "פורסם - ממתין לתשלום"),
    ("done",             "הושלם ✅"),
    ("not_interested",   "לא מעוניין"),
    ("not_relevant",     "לא רלוונטי"),
    ("lost",             "אבד"),
]
STATUS_KEYS = [s[0] for s in STATUSES]
INACTIVE = {"new", "no_answer", "not_interested", "not_relevant", "lost"}
SINK = {"not_relevant"}  # always sink to the bottom of the list regardless of sort
ACTIVE_KEYS = [k for k in STATUS_KEYS if k not in INACTIVE]

# WhatsApp templates per stage. {name} = business name, {demo} = demo url, {final} = final url.
TEMPLATES = {
    "new":              "שלום {name}, מדבר ליאם מ-DotCome. אני בונה אתרים לעסקים ויכול להכין לכם דמו של אתר *בחינם* כדי שתראו איך יכול להיראות. מתי נוח לדבר 2 דקות?",
    "no_answer":        "שלום {name}, ניסיתי להתקשר. מדבר ליאם מ-DotCome - אני מציע להכין לכם דמו אתר בחינם. אפשר לקבוע שיחה קצרה?",
    "interested":       "שלום {name}, תודה על השיחה! מתחיל לבנות עבורכם דמו של אתר ואשלח אליכם בקרוב.",
    "demo_built":       "שלום {name}, הדמו מוכן! אשלח קישור עוד מעט.",
    "demo_sent":        "שלום {name}, הדמו של האתר שלכם מוכן 🎉\n{demo}\nתסתכלו ותגידו לי מה אתם חושבים.",
    "followup":         "שלום {name}, רציתי לבדוק אם הספקתם להציץ בדמו ומה דעתכם 🙂\n{demo}",
    "offer_made":       "שלום {name}, מצרף שוב את ההצעה. אני זמין לכל שאלה.",
    "half_paid":        "שלום {name}, קיבלתי את התשלום הראשון, תודה! מתחיל בבנייה הסופית. אשמח לקבל את החומרים (לוגו, תמונות, טקסטים).",
    "collecting_assets":"שלום {name}, מזכיר ידידותי - מחכה לחומרים שלכם כדי להמשיך באתר 🙂",
    "finalizing":       "שלום {name}, האתר בשלבי סיום, אשלח אליכם בקרוב לאישור.",
    "published":        "שלום {name}, האתר עלה לאוויר! 🎉\n{final}\nממתין לתשלום הסופי כדי לסגור.",
    "done":             "שלום {name}, מקווה שאתם נהנים מהאתר! אם תצטרכו עדכונים או שינויים אני כאן.",
    "not_interested":   "תודה על הזמן {name}, בהצלחה!",
    "not_relevant":     "",
    "lost":             "",
}

def db():
    con = sqlite3.connect(DB, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")      # crash-safe, allows concurrent reads
    con.execute("PRAGMA synchronous=FULL")      # fsync every commit → survives power loss
    con.execute("PRAGMA foreign_keys=ON")
    return con

def to_intl(phone):
    if not phone: return None
    d = re.sub(r"\D", "", str(phone))
    if not d: return None
    if d.startswith("972"): return d
    if d.startswith("0"):   return "972" + d[1:]
    return d

# --- Audit / ownership ----------------------------------------------------
USER_KEYS = list(USERS.keys())

def current_user():
    return session.get("user") or "system"

def log_event(con, lead_id, action, details=None, user=None, ts=None):
    con.execute(
        "INSERT INTO lead_events (lead_id, user, action, details, created_at) "
        "VALUES (?,?,?,?, COALESCE(?, datetime('now','localtime')))",
        (lead_id, user or current_user(), action,
         json.dumps(details, ensure_ascii=False) if details is not None else None,
         ts),
    )

def ensure_schema():
    """Idempotent migration: add owner column, create lead_events table,
    randomly distribute existing leads across users, and seed historical
    events as liam so prior activity has an attribution."""
    con = db()
    cols = {r["name"] for r in con.execute("PRAGMA table_info(leads)").fetchall()}
    if "owner" not in cols:
        con.execute("ALTER TABLE leads ADD COLUMN owner TEXT")
    con.execute("CREATE INDEX IF NOT EXISTS idx_owner ON leads(owner)")

    con.execute("""
        CREATE TABLE IF NOT EXISTS lead_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            user TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_events_user ON lead_events(user)")

    unassigned = [r["id"] for r in con.execute("SELECT id FROM leads WHERE owner IS NULL").fetchall()]
    if unassigned:
        rng = random.Random(0xD07C0FFEE)
        rng.shuffle(unassigned)
        for i, lid in enumerate(unassigned):
            con.execute("UPDATE leads SET owner=? WHERE id=?", (USER_KEYS[i % len(USER_KEYS)], lid))

    has_events = con.execute("SELECT 1 FROM lead_events LIMIT 1").fetchone()
    if not has_events:
        for r in con.execute(
            "SELECT id, status, created_at, updated_at, last_contacted, owner FROM leads"
        ).fetchall():
            log_event(con, r["id"], "created",
                      {"owner": r["owner"]}, user="liam", ts=r["created_at"])
            if r["status"] and r["status"] != "new":
                log_event(con, r["id"], "status_change", {"to": r["status"]},
                          user="liam", ts=r["updated_at"] or r["created_at"])
            if r["last_contacted"]:
                log_event(con, r["id"], "called", None,
                          user="liam", ts=r["last_contacted"])
    con.close()

ensure_schema()

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip().lower()
        password = request.form.get("password") or ""
        if username in USERS and secrets.compare_digest(USERS[username], password):
            session.permanent = True
            session["auth"] = True
            session["user"] = username
            return redirect(request.args.get("next") or url_for("index"))
        error = "שם משתמש או סיסמה שגויים"
    return render_template("login.html", error=error)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    active_statuses = [(k, l) for k, l in STATUSES if k in ACTIVE_KEYS]
    return render_template("index.html", statuses=STATUSES, active_statuses=active_statuses)

@app.route("/api/me")
@login_required
def me():
    return jsonify({"user": session.get("user"), "users": USER_KEYS})

@app.route("/api/leads")
@login_required
def list_leads():
    q        = request.args.get("q", "").strip()
    status   = request.args.get("status", "").strip()
    city     = request.args.get("city", "").strip()
    category = request.args.get("category", "").strip()
    limit    = int(request.args.get("limit", 200))
    offset   = int(request.args.get("offset", 0))
    # multi-sort: sort=field1:asc,field2:desc  (advanced sorting)
    SORTABLE = {"updated_at","created_at","name","city","status","next_followup",
                "last_contacted","rating","reviews","price_total","price_paid","phone"}
    sort_raw = request.args.get("sort", "updated_at:desc")
    sort_parts = []
    for part in sort_raw.split(","):
        if ":" in part:
            f, d = part.split(":", 1)
        else:
            f, d = part, "desc"
        f = f.strip(); d = d.strip().lower()
        if f in SORTABLE and d in {"asc","desc"}:
            # push NULLs to the bottom regardless of direction
            sort_parts.append(f"CASE WHEN {f} IS NULL THEN 1 ELSE 0 END, {f} {d.upper()}")
    if not sort_parts:
        sort_parts = ["CASE WHEN updated_at IS NULL THEN 1 ELSE 0 END, updated_at DESC"]

    owner   = request.args.get("owner", "").strip()
    where, params = [], []
    if q:
        where.append("(name LIKE ? OR phone LIKE ? OR address LIKE ?)")
        like = f"%{q}%"
        params += [like, like, like]
    if status:
        where.append("status = ?")
        params.append(status)
    if city:
        where.append("city = ?")
        params.append(city)
    if category:
        where.append("category = ?")
        params.append(category)
    if owner:
        where.append("owner = ?")
        params.append(owner)
    if request.args.get("active") == "1":
        placeholders = ",".join("?" * len(ACTIVE_KEYS))
        where.append(f"status IN ({placeholders})")
        params.extend(ACTIVE_KEYS)
    sql = "SELECT * FROM leads"
    if where:
        sql += " WHERE " + " AND ".join(where)
    # Always sink "not_relevant" (and any future sink statuses) to the bottom
    sink_clause = "CASE WHEN status IN ({}) THEN 1 ELSE 0 END ASC".format(
        ",".join("?" * len(SINK))
    )
    sql += " ORDER BY " + sink_clause + ", " + ", ".join(sort_parts) + " LIMIT ? OFFSET ?"
    where_params = list(params)
    list_params = where_params + list(SINK) + [limit, offset]

    con = db()
    rows = [dict(r) for r in con.execute(sql, list_params).fetchall()]
    count_sql = "SELECT COUNT(*) FROM leads"
    if where:
        count_sql += " WHERE " + " AND ".join(where)
    total = con.execute(count_sql, where_params).fetchone()[0]

    # status counts for the sidebar
    counts = {row[0]: row[1] for row in con.execute("SELECT status, COUNT(*) FROM leads GROUP BY status").fetchall()}
    cities = [r[0] for r in con.execute("SELECT DISTINCT city FROM leads WHERE city IS NOT NULL ORDER BY city").fetchall()]
    categories = [r[0] for r in con.execute(
        "SELECT DISTINCT category FROM leads WHERE category IS NOT NULL AND category != '' ORDER BY category"
    ).fetchall()]
    owner_counts = {row[0]: row[1] for row in con.execute(
        "SELECT owner, COUNT(*) FROM leads WHERE owner IS NOT NULL GROUP BY owner"
    ).fetchall()}
    con.close()
    return jsonify({"leads": rows, "total": total, "counts": counts,
                    "cities": cities, "categories": categories,
                    "owner_counts": owner_counts,
                    "users": USER_KEYS})

@app.route("/api/leads", methods=["POST"])
@login_required
def create_lead():
    data = request.json or {}
    import uuid
    place_id = data.get("place_id") or f"manual_{uuid.uuid4().hex[:16]}"
    phone = data.get("phone")
    owner = (data.get("owner") or current_user()).strip().lower()
    if owner not in USERS:
        owner = current_user()
    con = db()
    con.execute(
        """INSERT INTO leads (place_id, name, category, city, phone, phone_intl, address, notes, status, owner)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            place_id,
            (data.get("name") or "").strip() or None,
            (data.get("category") or "").strip() or None,
            (data.get("city") or "").strip() or None,
            (phone or "").strip() or None,
            to_intl(phone),
            (data.get("address") or "").strip() or None,
            data.get("notes") or "",
            data.get("status") or "new",
            owner,
        ),
    )
    new_id = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    log_event(con, new_id, "created", {"owner": owner})
    r = con.execute("SELECT * FROM leads WHERE id=?", (new_id,)).fetchone()
    con.close()
    return jsonify(dict(r)), 201

@app.route("/api/leads/<int:lead_id>", methods=["GET"])
@login_required
def get_lead(lead_id):
    con = db()
    r = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    if not r: abort(404)
    return jsonify(dict(r))

@app.route("/api/leads/<int:lead_id>", methods=["PATCH"])
@login_required
def update_lead(lead_id):
    data = request.json or {}
    allowed = {"status","notes","next_followup","last_contacted","demo_url","final_url","price_total","price_paid","phone","owner"}
    fields = {k: v for k, v in data.items() if k in allowed}
    if not fields:
        return jsonify({"error": "no valid fields"}), 400
    if "status" in fields and fields["status"] not in STATUS_KEYS:
        return jsonify({"error": "bad status"}), 400
    if "owner" in fields:
        ow = (fields["owner"] or "").strip().lower()
        if ow not in USERS:
            return jsonify({"error": "bad owner"}), 400
        fields["owner"] = ow
    if "phone" in fields:
        fields["phone_intl"] = to_intl(fields["phone"])
    con = db()
    prev = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    if not prev:
        con.close()
        abort(404)
    sets = ", ".join(f"{k}=?" for k in fields) + ", updated_at=datetime('now','localtime')"
    con.execute(f"UPDATE leads SET {sets} WHERE id=?", (*fields.values(), lead_id))

    # Log the change in a way that's useful in the timeline
    if "status" in fields and fields["status"] != prev["status"]:
        log_event(con, lead_id, "status_change",
                  {"from": prev["status"], "to": fields["status"]})
    if "owner" in fields and fields["owner"] != prev["owner"]:
        log_event(con, lead_id, "owner_change",
                  {"from": prev["owner"], "to": fields["owner"]})
    other = {k: fields[k] for k in fields
             if k not in {"status", "owner", "phone_intl"} and fields[k] != prev[k]}
    if other:
        log_event(con, lead_id, "updated", {"fields": sorted(other.keys())})

    r = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    return jsonify(dict(r))

@app.route("/api/leads/<int:lead_id>/whatsapp")
@login_required
def whatsapp_link(lead_id):
    """Return a wa.me link with templated message for this lead's current (or requested) status."""
    con = db()
    r = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    if not r: abort(404)
    stage = request.args.get("stage", r["status"] or "new")
    tpl = TEMPLATES.get(stage, "")
    msg = tpl.format(
        name=(r["name"] or "").split(" - ")[0],
        demo=r["demo_url"] or "",
        final=r["final_url"] or "",
    )
    if not r["phone_intl"]:
        return jsonify({"error": "no phone"}), 400
    url = f"https://wa.me/{r['phone_intl']}?text={urllib.parse.quote(msg)}"
    return jsonify({"url": url, "message": msg})

@app.route("/api/leads/<int:lead_id>/log-call", methods=["POST"])
@login_required
def log_call(lead_id):
    data = request.get_json(silent=True) or {}
    channel = data.get("channel") or "call"  # "call" | "whatsapp"
    con = db()
    con.execute("UPDATE leads SET last_contacted=datetime('now','localtime'), updated_at=datetime('now','localtime') WHERE id=?", (lead_id,))
    log_event(con, lead_id, "called", {"channel": channel} if channel != "call" else None)
    r = con.execute("SELECT * FROM leads WHERE id=?", (lead_id,)).fetchone()
    con.close()
    return jsonify(dict(r))

@app.route("/api/leads/<int:lead_id>/events")
@login_required
def lead_events(lead_id):
    con = db()
    rows = con.execute(
        "SELECT user, action, details, created_at FROM lead_events "
        "WHERE lead_id=? ORDER BY datetime(created_at) DESC, id DESC",
        (lead_id,)
    ).fetchall()
    con.close()
    out = []
    for r in rows:
        d = dict(r)
        if d.get("details"):
            try:
                d["details"] = json.loads(d["details"])
            except (TypeError, ValueError):
                pass
        out.append(d)
    return jsonify(out)

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)
