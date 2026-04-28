"""One-shot importer: leads.xlsx -> crm.db (SQLite). Safe to re-run; will not overwrite existing CRM fields."""
import sqlite3, pandas as pd, re, os

DB = "crm.db"
XLSX = "leads.xlsx"

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id TEXT UNIQUE,
    name TEXT,
    category TEXT,
    city TEXT,
    phone TEXT,
    phone_intl TEXT,
    address TEXT,
    rating REAL,
    reviews REAL,
    primary_type TEXT,
    maps_url TEXT,
    status TEXT DEFAULT 'new',
    notes TEXT DEFAULT '',
    next_followup TEXT,
    last_contacted TEXT,
    demo_url TEXT,
    final_url TEXT,
    price_total REAL,
    price_paid REAL,
    owner TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_city ON leads(city);
CREATE INDEX IF NOT EXISTS idx_followup ON leads(next_followup);
CREATE INDEX IF NOT EXISTS idx_owner ON leads(owner);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL,
    user TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_events_lead ON lead_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_events_user ON lead_events(user);
"""

def to_intl(phone: str) -> str | None:
    if not phone or pd.isna(phone):
        return None
    digits = re.sub(r"\D", "", str(phone))
    if not digits:
        return None
    if digits.startswith("972"):
        return digits
    if digits.startswith("0"):
        return "972" + digits[1:]
    return digits

def main():
    new_db = not os.path.exists(DB)
    con = sqlite3.connect(DB)
    con.executescript(SCHEMA)

    df = pd.read_excel(XLSX)
    inserted = 0
    skipped = 0
    for _, r in df.iterrows():
        pid = r.get("place_id")
        if pd.isna(pid):
            continue
        cur = con.execute("SELECT 1 FROM leads WHERE place_id=?", (pid,))
        if cur.fetchone():
            skipped += 1
            continue
        phone = None if pd.isna(r.get("phone")) else str(r.get("phone"))
        con.execute(
            """INSERT INTO leads (place_id,name,category,city,phone,phone_intl,address,rating,reviews,primary_type,maps_url)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                pid,
                None if pd.isna(r.get("name")) else str(r.get("name")),
                None if pd.isna(r.get("category")) else str(r.get("category")),
                None if pd.isna(r.get("city")) else str(r.get("city")),
                phone,
                to_intl(phone),
                None if pd.isna(r.get("address")) else str(r.get("address")),
                None if pd.isna(r.get("rating")) else float(r.get("rating")),
                None if pd.isna(r.get("reviews")) else float(r.get("reviews")),
                None if pd.isna(r.get("primary_type")) else str(r.get("primary_type")),
                None if pd.isna(r.get("maps_url")) else str(r.get("maps_url")),
            ),
        )
        inserted += 1
    con.commit()
    total = con.execute("SELECT COUNT(*) FROM leads").fetchone()[0]
    con.close()
    print(f"{'Created' if new_db else 'Updated'} {DB}: inserted={inserted}, skipped(existing)={skipped}, total={total}")

if __name__ == "__main__":
    main()
