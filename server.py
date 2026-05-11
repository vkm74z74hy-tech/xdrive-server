from flask import Flask, request, jsonify
import sqlite3, os, datetime

app = Flask(__name__)
ADMIN_KEY = os.getenv("ADMIN_KEY", "changeme")
DB_PATH   = "xdrive.db"

# ─── DB setup ───────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                discord_id  TEXT PRIMARY KEY,
                hwid        TEXT,
                days        INTEGER DEFAULT 0,
                expiry_date TEXT,
                is_admin    INTEGER DEFAULT 0,
                is_lifetime INTEGER DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        db.commit()

init_db()

# ─── Auth check ─────────────────────────────────────────────────────────────

def check_admin_key(req):
    key = req.json.get("admin_key") if req.is_json else req.args.get("admin_key")
    return key == ADMIN_KEY

# ─── /validate  (called by xdriveps.py) ─────────────────────────────────────

@app.route("/validate", methods=["POST"])
def validate():
    data       = request.json
    discord_id = str(data.get("discord_id", "")).strip()
    hwid       = str(data.get("hwid", "")).strip()

    if not discord_id or not hwid:
        return jsonify(ok=False, message="Missing discord_id or hwid")

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()

    if not user:
        return jsonify(ok=False, message="No active subscription. Contact an admin.")

    # Lifetime check
    if user["is_lifetime"]:
        # Save HWID on first login
        if not user["hwid"]:
            with get_db() as db:
                db.execute("UPDATE users SET hwid = ? WHERE discord_id = ?", (hwid, discord_id))
                db.commit()
        elif user["hwid"] != hwid:
            return jsonify(ok=False, message="HWID mismatch. Ask an admin to reset.")
        return jsonify(ok=True, days_remaining="Lifetime")

    # Check expiry
    if not user["expiry_date"]:
        return jsonify(ok=False, message="No active subscription.")

    expiry = datetime.datetime.fromisoformat(user["expiry_date"])
    now    = datetime.datetime.utcnow()
    if now > expiry:
        return jsonify(ok=False, message="Subscription expired. Contact an admin to renew.")

    days_left = (expiry - now).days

    # HWID check
    if not user["hwid"]:
        with get_db() as db:
            db.execute("UPDATE users SET hwid = ? WHERE discord_id = ?", (hwid, discord_id))
            db.commit()
    elif user["hwid"] != hwid:
        return jsonify(ok=False, message="HWID mismatch. Ask an admin to reset.")

    return jsonify(ok=True, days_remaining=days_left, expiry_date=user["expiry_date"])

# ─── /add_days ───────────────────────────────────────────────────────────────

@app.route("/add_days", methods=["POST"])
def add_days():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    discord_id = str(request.json.get("discord_id", "")).strip()
    days       = int(request.json.get("days", 0))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
        now  = datetime.datetime.utcnow()

        if user:
            # Extend from existing expiry or from now, whichever is later
            if user["expiry_date"]:
                current = datetime.datetime.fromisoformat(user["expiry_date"])
                base    = current if current > now else now
            else:
                base = now
            new_expiry = base + datetime.timedelta(days=days)
            db.execute("UPDATE users SET expiry_date = ? WHERE discord_id = ?",
                (new_expiry.isoformat(), discord_id))
        else:
            # Create new user
            new_expiry = now + datetime.timedelta(days=days)
            db.execute("INSERT INTO users (discord_id, expiry_date) VALUES (?, ?)",
                (discord_id, new_expiry.isoformat()))
        db.commit()

    days_left = (new_expiry - now).days
    return jsonify(ok=True, total_days=days_left, expiry_date=new_expiry.isoformat())

# ─── /remove_days ────────────────────────────────────────────────────────────

@app.route("/remove_days", methods=["POST"])
def remove_days():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    discord_id = str(request.json.get("discord_id", "")).strip()
    days       = int(request.json.get("days", 0))

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
        if not user:
            return jsonify(ok=False, message="User not found")

        now    = datetime.datetime.utcnow()
        expiry = datetime.datetime.fromisoformat(user["expiry_date"]) if user["expiry_date"] else now
        new_expiry = expiry - datetime.timedelta(days=days)
        if new_expiry < now:
            new_expiry = now  # floor at now so it just expires immediately

        db.execute("UPDATE users SET expiry_date = ? WHERE discord_id = ?",
            (new_expiry.isoformat(), discord_id))
        db.commit()

    days_left = max(0, (new_expiry - now).days)
    return jsonify(ok=True, total_days=days_left, expiry_date=new_expiry.isoformat())

# ─── /reset_hwid ─────────────────────────────────────────────────────────────

@app.route("/reset_hwid", methods=["POST"])
def reset_hwid():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    discord_id = str(request.json.get("discord_id", "")).strip()

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
        if not user:
            return jsonify(ok=False, message="User not found")
        db.execute("UPDATE users SET hwid = NULL WHERE discord_id = ?", (discord_id,))
        db.commit()

    return jsonify(ok=True, message="HWID cleared")

# ─── /add_admin ──────────────────────────────────────────────────────────────

@app.route("/add_admin", methods=["POST"])
def add_admin():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    discord_id = str(request.json.get("discord_id", "")).strip()

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()
        if user:
            db.execute("UPDATE users SET is_admin = 1 WHERE discord_id = ?", (discord_id,))
        else:
            db.execute("INSERT INTO users (discord_id, is_admin) VALUES (?, 1)", (discord_id,))
        db.commit()

    return jsonify(ok=True, message="Admin added")

# ─── /get_admins ─────────────────────────────────────────────────────────────

@app.route("/get_admins", methods=["GET"])
def get_admins():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    with get_db() as db:
        rows = db.execute("SELECT discord_id FROM users WHERE is_admin = 1").fetchall()

    return jsonify(ok=True, admins=[r["discord_id"] for r in rows])

# ─── /check_user ─────────────────────────────────────────────────────────────

@app.route("/check_user", methods=["GET"])
def check_user():
    if not check_admin_key(request):
        return jsonify(ok=False, message="Unauthorized")

    discord_id = str(request.args.get("discord_id", "")).strip()

    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE discord_id = ?", (discord_id,)).fetchone()

    if not user:
        return jsonify(ok=False, message="User not found")

    if user["is_lifetime"]:
        return jsonify(ok=True, days_remaining="Lifetime", hwid=user["hwid"], expiry_date="None")

    now   = datetime.datetime.utcnow()
    expiry = datetime.datetime.fromisoformat(user["expiry_date"]) if user["expiry_date"] else now
    days_left = max(0, (expiry - now).days)

    return jsonify(
        ok=True,
        days_remaining=days_left,
        hwid=user["hwid"],
        expiry_date=user["expiry_date"] or "None"
    )

# ─── Run ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
