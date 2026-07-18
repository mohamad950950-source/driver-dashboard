#!/usr/bin/env python3
"""
Driver Revenue Dashboard — Multi-User (Owner + Drivers)
----------------------------------------
السواق بيسجل دخول ويشيف مشاويره وهو
المالك يشوف إجمالي كل السواقين وصافي الربح
"""
from __future__ import annotations
import sys, os, sqlite3, json, logging, csv, io, re, hashlib, secrets, random, string, binascii
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from typing import Any
from collections import defaultdict
from time import time

from fastapi import FastAPI, Request, HTTPException, Form
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi import Body
import uvicorn
from jinja2 import Environment, FileSystemLoader, select_autoescape
from translations import t as _t

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("driver-dash")

BASE = Path(__file__).resolve().parent
DATA_DIR = BASE / "data"
DATA_DIR.mkdir(exist_ok=True)

# ── Language helper ──
LANG_COOKIE = "driver_lang"
def get_lang(request: Request) -> str:
    return request.cookies.get(LANG_COOKIE, "ar")
def make_t(request: Request):
    lang = get_lang(request)
    return lambda key: _t(key, lang)

# ── Direct Jinja2 ──
jinja_env = Environment(
    loader=FileSystemLoader(str(BASE / "templates")),
    autoescape=select_autoescape(["html", "xml"])
)
def render(name: str, request: Request = None, **ctx) -> HTMLResponse:
    if request:
        ctx["_"] = make_t(request)
        ctx["lang"] = get_lang(request)
        ctx["dir"] = "rtl" if ctx["lang"] == "ar" else "ltr"
        ctx["request"] = request
    html = jinja_env.get_template(name).render(**ctx)
    return HTMLResponse(content=html)

app = FastAPI(title="Driver Revenue Dashboard", version="2.0.0")

# ── Config ──
DEBUG = os.getenv("DEBUG", "True").lower() in ("true", "1", "yes")
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")

# ── CORS (needed for React frontend) ──
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Rate Limiter (in-memory, for demo) ──
RATE_LIMIT_MAX = 5
RATE_LIMIT_WINDOW = 300  # 5 mins
OTP_ATTEMPT_WINDOW = 300
MAX_OTP_ATTEMPTS = 5
rate_limit_store = defaultdict(list)

def check_rate_limit(key: str, max_attempts: int, window_seconds: int) -> bool:
    now = time()
    rate_limit_store[key] = [t for t in rate_limit_store[key] if now - t < window_seconds]
    if len(rate_limit_store[key]) >= max_attempts:
        return False
    rate_limit_store[key].append(now)
    return True

UPLOADS_DIR = BASE / "uploads"
UPLOADS_DIR.mkdir(exist_ok=True)
static = StaticFiles(directory=str(BASE / "static"))
uploads = StaticFiles(directory=str(UPLOADS_DIR))
app.mount("/uploads", uploads, name="uploads")

# ── Database ──
from db import get_db as _get_db, USE_POSTGRES

def get_db():
    return _get_db()

def init_db():
    if USE_POSTGRES:
        from schema_pg import init_db_pg
        init_db_pg()
        logger.info("PostgreSQL schema initialized ✓")
        return
    # SQLite initialization (existing)
    with get_db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'driver' CHECK(role IN ('owner','driver')),
            phone TEXT DEFAULT '',
            driver_split_pct REAL DEFAULT 50,
            plate_number TEXT DEFAULT '',
            mobile TEXT DEFAULT '',
            national_id TEXT DEFAULT '',
            governorate TEXT DEFAULT '',
            car_verified INTEGER DEFAULT 0,
            license_photo TEXT DEFAULT '',
            car_reg_photo TEXT DEFAULT '',
            national_id_photo TEXT DEFAULT '',
            selfie_photo TEXT DEFAULT '',
            needs_setup INTEGER DEFAULT 0,
            display_name TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        -- Safe migration: add driver_of_owner if missing
        CREATE TABLE IF NOT EXISTS sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            expires_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS trips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            platform TEXT NOT NULL CHECK(platform IN ('uber','didi','indrive','personal')),
            date TEXT NOT NULL,
            start_time TEXT,
            end_time TEXT,
            fare REAL NOT NULL DEFAULT 0,
            tip REAL NOT NULL DEFAULT 0,
            commission REAL NOT NULL DEFAULT 0,
            distance_km REAL DEFAULT 0,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS fuel_fills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            odometer_km INTEGER DEFAULT 0,
            liters REAL DEFAULT 0,
            total_cost REAL DEFAULT 0,
            cost_per_liter REAL DEFAULT 0,
            notes TEXT DEFAULT '',
            photo_url TEXT DEFAULT '',
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            subcategory TEXT,
            amount REAL NOT NULL,
            date TEXT NOT NULL,
            notes TEXT,
            receipt_path TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS location_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            lat REAL NOT NULL,
            lng REAL NOT NULL,
            accuracy REAL DEFAULT 0,
            source TEXT DEFAULT '',
            recorded_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS maintenance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            cost REAL NOT NULL,
            borne_by TEXT NOT NULL DEFAULT 'owner' CHECK(borne_by IN ('driver','owner')),
            first_time_free INTEGER NOT NULL DEFAULT 0,
            odometer_km INTEGER,
            shop_name TEXT,
            next_service_km INTEGER,
            next_service_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS car_info (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS connected_accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL DEFAULT 0,
            platform TEXT NOT NULL CHECK(platform IN ('uber','didi','indrive')),
            status TEXT NOT NULL DEFAULT 'pending',
            auth_type TEXT NOT NULL DEFAULT 'oauth',
            token_data TEXT DEFAULT '{}',
            connected_at TEXT,
            last_sync TEXT,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL DEFAULT 0,
            driver_id INTEGER DEFAULT NULL,
            car_name TEXT DEFAULT '',
            plate_number TEXT DEFAULT '',
            fuel_type TEXT DEFAULT 'بنزين 95',
            fuel_cost_per_liter REAL DEFAULT 24,
            km_per_liter REAL DEFAULT 12,
            driver_split_pct REAL DEFAULT 50,
            partner_share_pct REAL DEFAULT 50,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            FOREIGN KEY(owner_id) REFERENCES users(id),
            FOREIGN KEY(driver_id) REFERENCES users(id)
        );
        CREATE TABLE IF NOT EXISTS otp_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT NOT NULL,
            code TEXT NOT NULL,
            used INTEGER NOT NULL DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            expires_at TEXT NOT NULL
        );
        INSERT OR IGNORE INTO car_info (key, value) VALUES
            ('car_name', ''),
            ('plate_number', ''),
            ('fuel_type', 'بنزين 95'),
            ('fuel_cost_per_liter', '24'),
            ('km_per_liter', '12'),
            ('partner_share_pct', '50'),
            ('currency', 'EGP'),
            ('oil_change_free_count', '1'),
            ('brake_service_free_count', '1'),
            ('oil_change_cost_est', '350'),
            ('brake_service_cost_est', '600'),
            ('driver_maintenance_types', 'تغيير زيت, فرامل'),
            ('promo_uber_commission', '25'),
            ('promo_didi_commission', '20'),
            ('promo_indrive_commission', '15'),
            ('promo_our_commission', '0'),
            ('promo_our_split', '50'),
            ('promo_banner', 'حلل أرباحك عبر كل المنصات في مكان واحد');
        """)
        # Migration: add driver_of_owner column if not exists
        try:
            conn.execute("ALTER TABLE users ADD COLUMN driver_of_owner INTEGER DEFAULT NULL")
        except:
            pass
        logger.info("DB initialized ✓")
init_db()

# ═══════════════════════════════════════════════════════════════════════════
# ── OTP AUTH SYSTEM ─────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

SESSION_COOKIE = "driver_sesh"
COOKIE_MAX_AGE = 60 * 60 * 24 * 7  # 7 days

def _generate_otp() -> str:
    """Generate 4-digit OTP code."""
    return str(random.randint(1000, 9999))

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, key_hex = stored.split(":")
        key = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 100000)
        return key.hex() == key_hex
    except (ValueError, IndexError, binascii.Error):
        logger.warning(f"Password verification failed")
        return False

def create_session(user_id: int) -> str:
    token = secrets.token_hex(32)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute("INSERT INTO sessions (user_id, token, expires_at) VALUES (?, ?, ?)",
                     (user_id, token, expires))
    logger.info(f"Session created for user {user_id}")
    return token

def get_current_user(request: Request) -> dict | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    with get_db() as conn:
        row = conn.execute(
            "SELECT u.id, u.username, u.email, u.role, u.driver_split_pct, u.display_name "
            "FROM sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token = ? AND s.expires_at > datetime('now', 'localtime')",
            (token,)
        ).fetchone()
    return dict(row) if row else None

# ═══════════════════════════════════════════════════════════════════════════
# ── AUTH ENDPOINTS ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/auth/owner-login")
def owner_login(data: dict):
    """Owner login: plate_number + phone -> login or auto-register."""
    plate = data.get("plate", "").strip().upper()
    phone = data.get("phone", "").strip()
    if not plate or not phone:
        raise HTTPException(400, "ادخل رقم العربية ورقم التلفون")

    # Rate limit: 5 attempts per 15 minutes
    if not check_rate_limit(f"owner_login:{plate}:{phone}", 5, 900):
        logger.warning(f"Rate limit exceeded for owner login: {plate}")
        raise HTTPException(429, "محاولات كتير — حاول بعد 15 دقيقة")

    user_id = None
    is_new = False
    with get_db() as conn:
        user = conn.execute(
            "SELECT * FROM users WHERE (role='owner' AND plate_number=?) OR (role='owner' AND mobile=?)",
            (plate, phone)
        ).fetchone()
        
        if not user:
            is_new = True
            pw_hash = hash_password(phone)
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash, role, plate_number, mobile, phone, display_name) VALUES (?,?,?,?,?,?,?,?)",
                (phone, f"{phone}@owner.local", pw_hash, "owner", plate, phone, phone, f"Owner {plate}")
            )
            user_id = cur.lastrowid
            # Auto-create a default car
            cur2 = conn.execute(
                "INSERT INTO cars (owner_id, car_name, plate_number, driver_split_pct) VALUES (?,?,?,?)",
                (user_id, f"Car {plate}", plate, 50)
            )
            car_id = cur2.lastrowid
            # Auto-create a driver account with same phone + assign to the car
            cur3 = conn.execute(
                "INSERT INTO users (username, email, password_hash, role, phone, mobile, display_name) VALUES (?,?,?, 'driver', ?, ?, ?)",
                (f"{phone}_driver", f"{phone}@driver.local", pw_hash, phone, phone, f"Owner {plate} (Driver)")
            )
            driver_id = cur3.lastrowid
            conn.execute("UPDATE cars SET driver_id=? WHERE id=?", (driver_id, car_id))
        else:
            user_id = user["id"]
    
    # Session created OUTSIDE the db context to avoid lock
    token = create_session(user_id)
    
    msg = "تسجيل جديد" if is_new else "تسجيل دخول"
    logger.info(f"Owner {msg}: {plate} / {phone}")
    
    resp = JSONResponse({
        "message": "تم تسجيل الدخول",
        "user": {"id": user_id, "role": "owner",
                 "plate_number": plate, "mobile": phone,
                 "display_name": f"Owner {plate}"}
    })
    resp.set_cookie(key=SESSION_COOKIE, value=token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="strict", secure=not DEBUG)
    return resp
@app.post("/api/auth/driver-login")
def driver_login(data: dict):
    """Driver logs in with just phone number. No OTP, no password.
    Owner can also login as driver using the same phone."""
    phone = data.get("phone", "").strip()
    if not phone or len(phone) < 10:
        raise HTTPException(400, "ادخل رقم تلفون صحيح (10 أرقام على الأقل)")

    with get_db() as conn:
        # Try to find as driver first
        user = conn.execute(
            "SELECT * FROM users WHERE (mobile=? OR phone=? OR username=?) AND role='driver'",
            (phone, phone, phone)
        ).fetchone()

        if not user:
            # Check if this is an owner trying to drive
            owner = conn.execute(
                "SELECT * FROM users WHERE (mobile=? OR phone=? OR username=?) AND role='owner'",
                (phone, phone, phone)
            ).fetchone()
            if owner:
                # Auto-create driver account for this owner
                owner_dict = dict(owner)
                pw_hash = hash_password(phone)
                display_name = owner_dict.get('display_name', '') or 'Owner'
                cur = conn.execute(
                    "INSERT INTO users (username, email, password_hash, role, phone, mobile, display_name) VALUES (?,?,?, 'driver', ?, ?, ?)",
                    (phone + "_driver", f"{phone}@driver.local", pw_hash, phone, phone, f"{display_name} (سواق)")
                )
                user_id = cur.lastrowid
                user = conn.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            else:
                raise HTTPException(404, "رقم التلفون مش موجود — المالك لازم يضيفك الأول")

        driver_id = user["id"]

    token = create_session(driver_id)
    logger.info(f"Driver login: {phone} (id={driver_id})")

    resp = JSONResponse({
        "message": "تم تسجيل الدخول",
        "user": {"id": driver_id, "role": "driver"}
    })
    resp.set_cookie(key=SESSION_COOKIE, value=token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="strict", secure=not DEBUG)
    return resp


@app.post("/api/auth/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        with get_db() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))
    resp = JSONResponse({"message": "تم تسجيل الخروج"})
    resp.delete_cookie(key=SESSION_COOKIE)
    return resp

# ═══════════════════════════════════════════════════════════════════════════
# ── OWNER: ADD DRIVER ───────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/owner/add-driver")
def owner_add_driver(request: Request, data: dict):
    """Owner adds ONE driver only. Owner is also a driver on the car."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403, "يجب أن تكون المالك")
    
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    car_id = data.get("car_id")
    
    if not name or not phone:
        raise HTTPException(400, "ادخل الاسم ورقم التلفون")
    if len(phone) < 10:
        raise HTTPException(400, "رقم التلفون غير صحيح")

    with get_db() as conn:
        # Check: owner can have at most 1 driver
        existing = conn.execute(
            "SELECT COUNT(*) as cnt FROM users WHERE role='driver' AND driver_of_owner=?",
            (user["id"],)
        ).fetchone()
        if existing and existing["cnt"] >= 1:
            raise HTTPException(400, "ممكن تضيف سواق واحد بس — المالك نفسه سواق على العربية")

        try:
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash, role, phone, mobile, display_name, needs_setup, driver_of_owner) VALUES (?, ?, ?, 'driver', ?, ?, ?, 1, ?)",
                (phone, f"{phone}@driver.local", hash_password(phone), phone, phone, name, user["id"])
            )
            driver_id = cur.lastrowid
            
            if car_id:
                car = conn.execute("SELECT * FROM cars WHERE id=? AND owner_id=?", (car_id, user["id"])).fetchone()
                if car:
                    conn.execute("UPDATE cars SET driver_id=? WHERE id=?", (driver_id, car_id))
            
            uid = user["id"]
            logger.info(f"Driver added: {name} / {phone} by owner {uid}")
            return {"message": f"تم إضافة {name} — {phone}", "driver_id": driver_id}
        except sqlite3.IntegrityError:
            raise HTTPException(400, "رقم التلفون مستخدم بالفعل")

@app.put("/api/owner/drivers/{driver_id}")
def owner_edit_driver(request: Request, driver_id: int, data: dict):
    """Owner edits a driver's name & phone."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    name = data.get("name", "").strip()
    phone = data.get("phone", "").strip()
    if not name or not phone:
        raise HTTPException(400, "ادخل الاسم ورقم التلفون")
    with get_db() as conn:
        driver = conn.execute("SELECT * FROM users WHERE id=? AND role='driver'", (driver_id,)).fetchone()
        if not driver:
            raise HTTPException(404, "السواق مش موجود")
        try:
            conn.execute("UPDATE users SET display_name=?, phone=?, mobile=? WHERE id=?", (name, phone, phone, driver_id))
            logger.info(f"Driver {driver_id} updated: {name} / {phone} by owner {user['id']}")
        except sqlite3.IntegrityError:
            raise HTTPException(400, "رقم التلفون مستخدم بالفعل")
        # Update username too if it matches old phone
        old_phone = driver["phone"]
        conn.execute("UPDATE users SET username=? WHERE id=? AND username=?", (phone, driver_id, old_phone))
    return {"message": f"تم تحديث {name}"}

@app.delete("/api/owner/drivers/{driver_id}")
def owner_delete_driver(request: Request, driver_id: int):
    """Owner deletes a driver (unassigns from car first)."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        driver = conn.execute("SELECT * FROM users WHERE id=? AND role='driver'", (driver_id,)).fetchone()
        if not driver:
            raise HTTPException(404, "السواق مش موجود")
        # Unassign from any car
        conn.execute("UPDATE cars SET driver_id=NULL WHERE driver_id=? AND owner_id=?", (driver_id, user["id"]))
        # Delete trips, expenses, fuel, maintenance for this driver
        conn.execute("DELETE FROM trips WHERE user_id=?", (driver_id,))
        conn.execute("DELETE FROM expenses WHERE user_id=?", (driver_id,))
        conn.execute("DELETE FROM fuel_fills WHERE user_id=?", (driver_id,))
        conn.execute("DELETE FROM maintenance WHERE user_id=?", (driver_id,))
        # Delete sessions
        conn.execute("DELETE FROM sessions WHERE user_id=?", (driver_id,))
        # Delete the user
        conn.execute("DELETE FROM users WHERE id=?", (driver_id,))
        logger.info(f"Driver {driver_id} ({driver['display_name']}) deleted by owner {user['id']}")
    return {"message": "تم حذف السواق"}

@app.post("/api/auth/dev-login")
def dev_login(data: dict):
    """Dev mode: login with role only — creates test accounts if needed."""
    if not DEBUG:
        logger.warning(f"Dev login attempted in production from!")
        raise HTTPException(403, "Dev login is disabled in production")
    role = data.get("role", "driver")
    if role not in ("owner", "driver"):
        raise HTTPException(400, "")
    username = f"dev_{role}"
    password = "devpass"
    with get_db() as conn:
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not user:
            pw_hash = hash_password(password)
            cur = conn.execute(
                "INSERT INTO users (username, email, password_hash, role, phone, display_name, driver_split_pct) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (username, f"{username}@dev.local", pw_hash, role, username, f"Dev {role}", 50)
            )
            uid = cur.lastrowid
            if role == "owner":
                for k,v in [('car_name','Dev Car'),('plate_number','DEV 123'),('fuel_type','بنزين 95'),('fuel_cost_per_liter','24'),('km_per_liter','12'),('partner_share_pct','50'),('setup_complete','true')]:
                    conn.execute("INSERT OR REPLACE INTO car_info (key,value) VALUES (?,?)", (k,v))
        else:
            uid = user["id"]
    token = create_session(uid)
    resp = JSONResponse({"message": f"Dev {role}", "user": {"username": username, "role": role}})
    resp.set_cookie(key=SESSION_COOKIE, value=token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="strict", secure=not DEBUG)
    return resp

@app.get("/api/health")
def health():
    return {"status": "ok", "version": "2.0.0"}

@app.get("/api/auth/me")
def auth_me(request: Request):
    user = get_current_user(request)
    if user:
        # Get full profile
        with get_db() as conn:
            full = conn.execute(
                "SELECT id, username, email, role, driver_split_pct, plate_number, mobile, national_id, governorate, car_verified, created_at FROM users WHERE id=?",
                (user["id"],)
            ).fetchone()
        if full:
            return {"authenticated": True, "user": dict(full)}
    return {"authenticated": False, "user": None}

# ═══════════════════════════════════════════════════════════════════════════
# ── OWNER DASHBOARD — Aggregate all drivers ──────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/owner/summary")
def owner_summary(request: Request, period: str = "month"):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403, "يجب أن تكون المالك")
    
    # Safe: period is validated against dict keys
    safe_periods = {"week": "-7 days", "month": "-30 days", "year": "-365 days"}
    days_offset = safe_periods.get(period, "-30 days")
    date_sql = "1=1" if period == "all" else f"date >= date('now', 'localtime', ?)"
    date_param = [] if period == "all" else [days_offset]

    with get_db() as conn:
        drivers_raw = conn.execute(
            f"SELECT u.id, u.driver_split_pct, u.display_name, u.username,"
            f" COUNT(t.id) as trip_count,"
            f" COALESCE(SUM(t.fare + t.tip - t.commission),0) as gross_revenue,"
            f" COALESCE(SUM(t.distance_km),0) as total_km,"
            f" COALESCE(SUM(t.fare),0) as total_fare,"
            f" COALESCE(SUM(t.tip),0) as total_tip,"
            f" COALESCE(SUM(t.commission),0) as total_commission,"
            f" COALESCE((SELECT SUM(e.amount) FROM expenses e WHERE e.user_id = u.id AND {date_sql}),0) as total_expenses,"
            f" COALESCE((SELECT SUM(m.cost) FROM maintenance m WHERE m.user_id = u.id AND {date_sql}),0) as total_maintenance"
            f" FROM users u"
            f" LEFT JOIN trips t ON t.user_id = u.id AND {date_sql}"
            f" WHERE u.role = 'driver'"
            f" GROUP BY u.id ORDER BY gross_revenue DESC",
            date_param * 3  # reused 3 times in the query
        ).fetchall()
        
        car_info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}
        partner_pct = float(car_info.get("partner_share_pct", 50))
        km_per_liter = float(car_info.get("km_per_liter", 12))
        fuel_cost = float(car_info.get("fuel_cost_per_liter", 24))

        drivers = []
        total_gross = 0; total_km = 0; total_driver_expenses = 0; total_driver_maint = 0

        for d in drivers_raw:
            dd = dict(d)
            driver_pct = dd["driver_split_pct"]
            net_trip = dd["gross_revenue"]
            total_gross += net_trip; total_km += dd["total_km"]
            total_driver_expenses += dd["total_expenses"]; total_driver_maint += dd["total_maintenance"]
            driver_share = round(net_trip * driver_pct / 100, 2)
            owner_gross = net_trip - driver_share
            partner_share = round(owner_gross * partner_pct / 100, 2) if partner_pct > 0 else 0
            owner_net_share = owner_gross - partner_share
            dd["driver_share"] = driver_share; dd["owner_gross_from_driver"] = round(owner_gross, 2)
            dd["partner_share_from_driver"] = round(partner_share, 2); dd["owner_net_from_driver"] = round(owner_net_share, 2)
            drivers.append(dd)

        fuel_est = (total_km / km_per_liter * fuel_cost) if km_per_liter > 0 and total_km > 0 else 0
        total_expenses_raw = conn.execute(f"SELECT COALESCE(SUM(amount),0) FROM expenses WHERE {date_sql}", date_param).fetchone()[0]
        total_maint_raw = conn.execute(f"SELECT COALESCE(SUM(cost),0) FROM maintenance WHERE {date_sql}", date_param).fetchone()[0]

        logger.info(f"Owner {user['id']} viewed summary for period={period}")

        return {
            "drivers": drivers,
            "total_gross": round(total_gross, 2),
            "total_km": round(total_km, 1),
            "total_driver_expenses": round(total_driver_expenses, 2),
            "total_driver_maint": round(total_driver_maint, 2),
            "fuel_estimate": round(fuel_est, 2),
            "total_costs": round(total_driver_expenses + total_driver_maint + fuel_est, 2),
            "partner_share_pct": partner_pct,
            "driver_count": len(drivers),
            "car_info": car_info,
        }

@app.get("/api/owner/drivers")
def owner_list_drivers(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403, "يجب أن تكون المالك")
    with get_db() as conn:
        # Get owner's cars with assigned drivers
        cars = conn.execute("""
            SELECT c.id as car_id, c.car_name, c.plate_number, c.driver_split_pct,
                   u.id as driver_id, u.username, u.display_name, u.phone, u.mobile
            FROM cars c
            LEFT JOIN users u ON u.id = c.driver_id
            WHERE c.owner_id = ?
            ORDER BY c.id
        """, (user["id"],)).fetchall()
    return {"cars": [dict(c) for c in cars]}

@app.get("/api/owner/drivers-list")
def owner_list_drivers_only(request: Request):
    """Return just drivers (not cars) for this owner."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        drivers = conn.execute("""
            SELECT u.id, u.username, u.display_name, u.phone, u.mobile,
                   c.id as car_id, c.car_name, c.plate_number
            FROM users u
            LEFT JOIN cars c ON c.driver_id = u.id AND c.owner_id = ?
            WHERE u.role = 'driver'
            ORDER BY u.display_name, u.username
        """, (user["id"],)).fetchall()
    return {"drivers": [dict(d) for d in drivers]}

@app.post("/api/owner/cars")
def owner_add_car(request: Request, data: dict):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO cars (owner_id, car_name, plate_number, fuel_type, fuel_cost_per_liter, km_per_liter, driver_split_pct) VALUES (?,?,?,?,?,?,?)",
            (user["id"], data.get("car_name", "عربية جديدة"), data.get("plate_number", ""),
             data.get("fuel_type", "بنزين 95"), float(data.get("fuel_cost_per_liter", 24)),
             float(data.get("km_per_liter", 12)), float(data.get("driver_split_pct", 50)))
        )
        car_id = cur.lastrowid
    return {"car_id": car_id, "message": "تمت إضافة العربية"}

@app.post("/api/owner/cars/{car_id}/assign")
def owner_assign_driver(request: Request, car_id: int, data: dict):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    driver_phone = data.get("phone", "")
    if not driver_phone:
        raise HTTPException(400, "ادخل رقم تلفون السواق")
    with get_db() as conn:
        car = conn.execute("SELECT * FROM cars WHERE id=? AND owner_id=?", (car_id, user["id"])).fetchone()
        if not car:
            raise HTTPException(404, "العربية مش موجودة")
        # Find driver by phone
        driver = conn.execute("SELECT id, username FROM users WHERE (phone=? OR mobile=? OR username=?) AND role='driver'", (driver_phone, driver_phone, driver_phone)).fetchone()
        if not driver:
            driver = conn.execute("SELECT id, username FROM users WHERE (phone=? OR mobile=? OR username=?)", (driver_phone, driver_phone, driver_phone)).fetchone()
        if not driver:
            raise HTTPException(404, "السواق مش موجود. لازم يسجل الأول")
        conn.execute("UPDATE cars SET driver_id=? WHERE id=?", (driver["id"], car_id))
    return {"message": f"تم تعيين {driver['username']} على العربية", "driver_id": driver["id"]}

@app.post("/api/owner/cars/{car_id}/unassign")
def owner_unassign_driver(request: Request, car_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        conn.execute("UPDATE cars SET driver_id=NULL WHERE id=? AND owner_id=?", (car_id, user["id"]))
    return {"message": "تم فك ربط السواق"}

@app.delete("/api/owner/cars/{car_id}")
def owner_delete_car(request: Request, car_id: int):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        conn.execute("DELETE FROM cars WHERE id=? AND owner_id=?", (car_id, user["id"]))
    return {"message": "تم حذف العربية"}

@app.get("/api/owner/partner-share")
def get_partner_share(request: Request):
    """Get partner share percentage."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        val = conn.execute(
            "SELECT value FROM car_info WHERE key='partner_share_pct'"
        ).fetchone()
    return {"partner_share_pct": float(val[0]) if val else 50}

@app.post("/api/owner/partner-share")
def set_partner_share(request: Request, data: dict):
    """Set partner share percentage."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    pct = float(data.get("partner_share_pct", 50))
    if pct < 0 or pct > 100:
        raise HTTPException(400, "النسبة بين 0 و 100")
    with get_db() as conn:
        conn.execute("INSERT OR REPLACE INTO car_info (key, value) VALUES ('partner_share_pct', ?)", (str(pct),))
    logger.info(f"Partner share updated to {pct}% by owner {user['id']}")
    return {"partner_share_pct": pct}

@app.get("/api/owner/cars")
def owner_list_cars(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        cars = conn.execute("""
            SELECT c.id as car_id, c.*, u.username as driver_name, u.display_name, u.phone as driver_phone
            FROM cars c
            LEFT JOIN users u ON u.id = c.driver_id
            WHERE c.owner_id = ?
            ORDER BY c.id
        """, (user["id"],)).fetchall()
    return {"cars": [dict(c) for c in cars]}

@app.get("/api/owner/driver-trips/{driver_id}")
def owner_driver_trips(request: Request, driver_id: int, days: int = 30):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM trips WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days') ORDER BY date DESC",
            (driver_id, f"-{days}")
        ).fetchall()
    return {"data": [dict(r) for r in rows]}

# ═══════════════════════════════════════════════════════════════════════════
# ── DRIVER — Own Data ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/trips")
def list_trips(request: Request, platform: str = None, days: int = 30, offset: int = 0, limit: int = 100):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "سجل دخول أولاً")
    with get_db() as conn:
        where = ["user_id = ?"]
        params = [user["id"]]
        if platform and platform != 'all':
            where.append("platform = ?")
            params.append(platform)
        where.append("date >= date('now', 'localtime', ? || ' days')")
        params.append(f"-{days}")
        w = " AND ".join(where)
        rows = conn.execute(
            f"SELECT * FROM trips WHERE {w} ORDER BY date DESC, id DESC LIMIT ? OFFSET ?",
            params + [limit, offset]
        ).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM trips WHERE {w}", params).fetchone()[0]
    return {"data": [dict(r) for r in rows], "total": total}

@app.post("/api/trips")
def add_trip(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    required = ["platform", "date", "fare"]
    for k in required:
        if k not in data:
            raise HTTPException(400, f"Missing: {k}")
    fare = float(data["fare"])
    tip = float(data.get("tip", 0))
    commission = float(data.get("commission", 0))
    distance_km = float(data.get("distance_km", 0))
    if fare < 0 or tip < 0 or commission < 0 or distance_km < 0:
        raise HTTPException(400, "القيم لا يمكن أن تكون سالبة")
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO trips (user_id, platform, date, start_time, end_time, fare, tip, commission, distance_km, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (user["id"], data["platform"], data["date"], data.get("start_time",""), data.get("end_time",""),
             fare, tip, commission, distance_km, data.get("notes",""))
        )
        return {"id": cur.lastrowid, "message": "تمت الإضافة "}

@app.delete("/api/trips/{trip_id}")
def delete_trip(request: Request, trip_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        conn.execute("DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, user["id"]))
    return {"message": "تم الحذف"}

@app.get("/api/driver-summary")
def driver_summary(request: Request, period: str = "month"):
    """Driver sees their own summary with split calculations."""
    user = get_current_user(request)
    if not user or user["role"] != "driver":
        raise HTTPException(403)
    
    date_cond_map = {"today": "-0 days", "week": "-7 days", "month": "-30 days", "year": "-365 days"}
    date_cond = date_cond_map.get(period, "-30 days")
    date_sql = f"date = date('now', 'localtime')" if period == "today" else (f"date >= date('now', 'localtime', '{date_cond}')" if period != "all" else "1=1")

    with get_db() as conn:
        rev = conn.execute(f"""
            SELECT platform, COUNT(*) as trip_count,
                   COALESCE(SUM(fare+tip-commission),0) as net_revenue,
                   COALESCE(SUM(fare),0) as total_fare,
                   COALESCE(SUM(tip),0) as total_tip,
                   COALESCE(SUM(commission),0) as total_commission,
                   COALESCE(SUM(distance_km),0) as total_km,
                   COALESCE(AVG(fare),0) as avg_fare
            FROM trips WHERE user_id = ? AND {date_sql}
            GROUP BY platform
        """, (user["id"],)).fetchall()

        total_net = conn.execute(f"""
            SELECT COALESCE(SUM(fare+tip-commission),0) FROM trips WHERE user_id = ? AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        total_exp = conn.execute(f"""
            SELECT COALESCE(SUM(amount),0) FROM expenses WHERE user_id = ? AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        total_maint = conn.execute(f"""
            SELECT COALESCE(SUM(cost),0) FROM maintenance WHERE user_id = ? AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        # Separate driver-borne vs owner-borne maintenance
        driver_maint = conn.execute(f"""
            SELECT COALESCE(SUM(cost),0) FROM maintenance 
            WHERE user_id = ? AND borne_by='driver' AND first_time_free=0 AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        owner_maint = conn.execute(f"""
            SELECT COALESCE(SUM(cost),0) FROM maintenance 
            WHERE user_id = ? AND borne_by='owner' AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        # First-time free maintenance (owner provided, not billed to anyone)
        free_maint = conn.execute(f"""
            SELECT COALESCE(SUM(cost),0) FROM maintenance 
            WHERE user_id = ? AND first_time_free=1 AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        total_km_val = conn.execute(f"""
            SELECT COALESCE(SUM(distance_km),0) FROM trips WHERE user_id = ? AND {date_sql}
        """, (user["id"],)).fetchone()[0]

        # Daily chart
        daily = conn.execute(f"""
            SELECT date, COALESCE(SUM(fare+tip-commission),0) as net
            FROM trips WHERE user_id = ? AND {date_sql}
            GROUP BY date ORDER BY date
        """, (user["id"],)).fetchall()

        # Platform breakdown
        platforms_brk = conn.execute(f"""
            SELECT platform, COALESCE(SUM(fare+tip-commission),0) as net
            FROM trips WHERE user_id = ? AND {date_sql}
            GROUP BY platform
        """, (user["id"],)).fetchall()

        # Car info (for fuel estimate)
        car_info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}

    # Fuel estimate — use real data if available, else estimate
    try:
        kmpl = float(car_info.get("km_per_liter", 12))
        fcost = float(car_info.get("fuel_cost_per_liter", 24))
        est_fuel = (total_km_val / kmpl * fcost) if kmpl > 0 else 0
    except:
        est_fuel = 0

    # Check real fuel fills (same period as trips)
    with get_db() as conn:
        fills = conn.execute(
            f"SELECT COALESCE(SUM(liters),0), COALESCE(SUM(total_cost),0) FROM fuel_fills WHERE user_id = ? AND {date_sql}",
            (user["id"],)
        ).fetchone()
    real_liters = fills[0] if fills else 0
    real_cost = fills[1] if fills else 0
    use_real_fuel = real_cost > 0
    fuel_estimate = round(real_cost, 2) if use_real_fuel else round(est_fuel, 2)

    # Split calculation — maintenance logic:
    # 1. Total trip revenue
    # 2. Subtract owner-borne maintenance (tires, AC, electrical, etc.)
    # 3. Split remaining: driver gets driver_pct%, owner gets the rest
    # 4. From driver's share, subtract driver-borne maintenance (oil, brakes after first free)
    net_after_owner_maint = total_net - owner_maint
    driver_pct = user["driver_split_pct"]
    driver_share_before = round(net_after_owner_maint * driver_pct / 100, 2)
    driver_share = round(driver_share_before - driver_maint, 2)
    owner_share = round(net_after_owner_maint - driver_share_before, 2)

    partner_pct = float(car_info.get("partner_share_pct", 50))
    partner_share = round(owner_share * partner_pct / 100, 2) if partner_pct > 0 else 0
    owner_net_from_me = round(owner_share - partner_share, 2)

    total_costs = round(total_exp + driver_maint + fuel_estimate, 2)
    net_profit = round(driver_share - total_costs, 2)

    return {
        "revenue": [dict(r) for r in rev],
        "total_net_revenue": total_net,
        "total_km": total_km_val,
        "total_expenses": total_exp,
        "total_maintenance": total_maint,
        "driver_borne_maint": round(driver_maint, 2),
        "owner_borne_maint": round(owner_maint, 2),
        "free_first_maint": round(free_maint, 2),
        "net_after_owner_maint": round(net_after_owner_maint, 2),
        "fuel_estimate": fuel_estimate,
        "use_real_fuel": use_real_fuel,
        "total_costs": total_costs,
        "net_profit": net_profit,
        "driver_split_pct": driver_pct,
        "your_share": driver_share,
        "owner_share": owner_share,
        "partner_share_from_you": partner_share,
        "daily": [dict(r) for r in daily],
        "platforms_breakdown": [dict(r) for r in platforms_brk],
        "car_info": car_info,
    }

@app.get("/api/expenses")
def list_expenses(request: Request, days: int = 30):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days') ORDER BY date DESC",
            (user["id"], f"-{days}")
        ).fetchall()
    return {"data": [dict(r) for r in rows]}

@app.post("/api/expenses")
def add_expense(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, amount, date, notes) VALUES (?,?,?,?,?,?)",
            (user["id"], data["category"], data.get("subcategory",""), float(data["amount"]), data["date"], data.get("notes",""))
        )
        return {"id": cur.lastrowid, "message": "تمت الإضافة "}

@app.delete("/api/expenses/{exp_id}")
def delete_expense(request: Request, exp_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        conn.execute("DELETE FROM expenses WHERE id = ? AND user_id = ?", (exp_id, user["id"]))
    return {"message": "تم الحذف"}

@app.get("/api/maintenance")
def list_maintenance(request: Request, days: int = 365):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM maintenance WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days') ORDER BY date DESC",
            (user["id"], f"-{days}")
        ).fetchall()
    return {"data": [dict(r) for r in rows]}

@app.post("/api/maintenance")
def add_maintenance(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    
    # Auto-detect who bears the cost
    maint_type = data["type"]
    driver_types = ["تغيير زيت", "فرامل"]
    borne_by = "driver" if maint_type in driver_types else "owner"
    
    # Check if this is first-time free (owner provides materials first time)
    first_time_free = 0
    if borne_by == "driver":
        with get_db() as conn:
            car_info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}
            existing = conn.execute(
                "SELECT COUNT(*) FROM maintenance WHERE user_id = ? AND type = ?",
                (user["id"], maint_type)
            ).fetchone()[0]
            free_count = int(car_info.get("oil_change_free_count", 1)) if maint_type == "تغيير زيت" else int(car_info.get("brake_service_free_count", 1))
            if existing < free_count:
                first_time_free = 1
                borne_by = "owner"
    
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO maintenance (user_id, date, type, description, cost, borne_by, first_time_free, odometer_km, shop_name, next_service_km, next_service_date, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (user["id"], data["date"], maint_type, data.get("description",""), float(data["cost"]),
             borne_by, first_time_free,
             int(data.get("odometer_km",0)) if data.get("odometer_km") else None,
             data.get("shop_name",""),
             int(data.get("next_service_km",0)) if data.get("next_service_km") else None,
             data.get("next_service_date",""), data.get("notes",""))
        )
        # Also record as expense (only if borne by driver or always record)
        exp_category = maint_type if maint_type in ("زيت", "إطارات", "غسيل", "فرامل") else "صيانة"
        conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, amount, date, notes) VALUES (?,?,?,?,?,?)",
            (user["id"], exp_category, maint_type, float(data["cost"]), data["date"], data.get("notes",""))
        )
    msg = "تمت الإضافة "
    if first_time_free:
        msg += f" — أول {maint_type} مجاني من المالك "
    elif borne_by == "driver":
        msg += f" — على حساب السواق (يتم خصمها)"
    return {"id": cur.lastrowid, "message": msg}

@app.delete("/api/maintenance/{maint_id}")
def delete_maintenance(request: Request, maint_id: int):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        conn.execute("DELETE FROM maintenance WHERE id = ? AND user_id = ?", (maint_id, user["id"]))
    return {"message": "تم الحذف"}

# ═══════════════════════════════════════════════════════════════════════════
# ── FUEL TRACKING ───────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/api/fuel")
def list_fuel(request: Request, days: int = 365):
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM fuel_fills WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days') ORDER BY date DESC, id DESC",
            (user["id"], f"-{days}")
        ).fetchall()
    return {"data": [dict(r) for r in rows]}

@app.post("/api/fuel")
def add_fuel(request: Request, data: dict):
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    required = ["date", "odometer_km", "liters", "total_cost"]
    for k in required:
        if k not in data: raise HTTPException(400, f"مفقود: {k}")
    odometer = int(data["odometer_km"])
    liters = float(data["liters"])
    total = float(data["total_cost"])
    cost_per_liter = round(total / liters, 2) if liters > 0 else 0
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO fuel_fills (user_id, date, odometer_km, liters, cost_per_liter, total_cost, notes) VALUES (?,?,?,?,?,?,?)",
            (user["id"], data["date"], odometer, liters, cost_per_liter, total, data.get("notes",""))
        )
        # Also record as expense
        conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, amount, date, notes) VALUES (?,?,?,?,?,?)",
            (user["id"], "بنزين", f"{liters} لتر", total, data["date"], data.get("notes",""))
        )
    return {"id": cur.lastrowid, "message": " تم تسجيل التموينة", "cost_per_liter": cost_per_liter}

@app.delete("/api/fuel/{fuel_id}")
def delete_fuel(request: Request, fuel_id: int):
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        conn.execute("DELETE FROM fuel_fills WHERE id = ? AND user_id = ?", (fuel_id, user["id"]))
    return {"message": "تم الحذف"}

@app.get("/api/fuel/stats")
def fuel_stats(request: Request, days: int = 30):
    """Calculate real fuel consumption from actual fills + trip KMs."""
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        # Get fills in period
        fills = conn.execute(
            "SELECT * FROM fuel_fills WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days') ORDER BY date ASC",
            (user["id"], f"-{days}")
        ).fetchall()
        # Get total trip KM in period
        total_km = conn.execute(
            "SELECT COALESCE(SUM(distance_km),0) FROM trips WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days')",
            (user["id"], f"-{days}")
        ).fetchone()[0]

    total_liters = sum(f["liters"] for f in fills)
    total_cost = sum(f["total_cost"] for f in fills)
    fill_count = len(fills)

    km_per_liter = round(total_km / total_liters, 1) if total_liters > 0 else 0
    cost_per_km = round(total_cost / total_km, 2) if total_km > 0 else 0
    real_fuel_est = round(total_km * cost_per_km, 2) if cost_per_km > 0 else 0
    
    # Last odometer reading
    last_odo = fills[-1]["odometer_km"] if fills else 0
    first_odo = fills[0]["odometer_km"] if fills else 0
    odo_diff = last_odo - first_odo

    return {
        "total_km": round(total_km, 1),
        "total_liters": round(total_liters, 2),
        "total_cost": round(total_cost, 2),
        "fill_count": fill_count,
        "km_per_liter": km_per_liter,
        "cost_per_km": cost_per_km,
        "real_fuel_est": real_fuel_est,
        "last_odo": last_odo,
        "odo_diff": odo_diff,
    }

# ── LOCATION TRACKING ─────────────────────────────────────────────────

@app.post("/api/location")
def log_location(request: Request, data: dict):
    user = get_current_user(request)
    if not user or user["role"] != "driver":
        raise HTTPException(403)
    with get_db() as conn:
        conn.execute(
            "INSERT INTO location_logs (user_id, lat, lng, accuracy, source) VALUES (?, ?, ?, ?, ?)",
            (user["id"], data["lat"], data["lng"], data.get("accuracy", 0), data.get("source", ""))
        )
    return {"message": "تم تسجيل الموقع"}

@app.get("/api/location/latest")
def latest_location(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        if user["role"] == "owner":
            rows = conn.execute(
                "SELECT l.*, u.username FROM location_logs l "
                "JOIN users u ON l.user_id = u.id "
                "WHERE l.id IN (SELECT MAX(id) FROM location_logs GROUP BY user_id) "
                "ORDER BY l.recorded_at DESC"
            ).fetchall()
            return {"locations": [dict(r) for r in rows]}
        else:
            row = conn.execute(
                "SELECT * FROM location_logs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user["id"],)
            ).fetchone()
            return {"location": dict(row) if row else None}

# ═══════════════════════════════════════════════════════════════════════════
# ── DOCUMENT UPLOAD & VERIFICATION ──────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.post("/api/upload-document")
async def upload_document(request: Request):
    """Upload a verification document (license, car reg, national ID, selfie)."""
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    form = await request.form()
    doc_type = form.get("doc_type", "")
    if doc_type not in ("license_photo", "car_reg_photo", "national_id_photo", "selfie_photo"):
        raise HTTPException(400, "نوع مستند غير معروف")
    file = form.get("file")
    if not file: raise HTTPException(400, "لم يتم رفع ملف")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "الملف كبير جداً")
    ext = "jpg"
    if file.filename:
        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else "jpg"
        if ext not in ("jpg", "jpeg", "png", "gif", "webp"): ext = "jpg"
    fname = f"doc_{user['id']}_{doc_type}.{ext}"
    fpath = UPLOADS_DIR / fname
    with open(fpath, "wb") as f:
        f.write(content)
    with get_db() as conn:
        conn.execute(f"UPDATE users SET {doc_type}=? WHERE id=?", (f"/uploads/{fname}", user["id"]))
    return {"message": f" تم رفع المستند", "url": f"/uploads/{fname}"}

@app.get("/api/driver-documents/{driver_id}")
def get_driver_documents(request: Request, driver_id: int):
    """Owner views a driver's uploaded documents."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, username, plate_number, mobile, national_id, governorate, "
            "license_photo, car_reg_photo, national_id_photo, selfie_photo, car_verified "
            "FROM users WHERE id=? AND role='driver'", (driver_id,)
        ).fetchone()
    if not row: raise HTTPException(404)
    return dict(row)

@app.post("/api/verify-driver/{driver_id}")
def verify_driver(request: Request, driver_id: int, data: dict = Body({"status": 1})):
    """Owner approves or rejects a driver's verification."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        raise HTTPException(403)
    new_status = data.get("status", 1)
    with get_db() as conn:
        conn.execute("UPDATE users SET car_verified=? WHERE id=? AND role='driver'",
                     (new_status, driver_id))
    msg = "تم التوثيق " if new_status else "تم إلغاء التوثيق "
    return {"message": msg, "car_verified": new_status}

@app.get("/api/car-settings")
def get_car_settings(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}
    if user["role"] == "driver":
        info["my_split_pct"] = str(user["driver_split_pct"])
    return info

@app.post("/api/car-settings")
def save_car_settings(request: Request, data: dict):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        for k, v in data.items():
            conn.execute("INSERT OR REPLACE INTO car_info (key, value) VALUES (?,?)", (k, str(v)))
        # If driver is updating their split
        if "my_split_pct" in data and user["role"] == "driver":
            conn.execute("UPDATE users SET driver_split_pct = ? WHERE id = ?",
                         (float(data["my_split_pct"]), user["id"]))
    return {"message": "تم الحفظ "}

@app.get("/api/export/{format}")
def export_data(request: Request, format: str = "json", period: str = "month"):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    date_cond = f"date >= date('now', 'localtime', '-{30 if period=='month' else 7 if period=='week' else 365} days')"
    with get_db() as conn:
        trips = conn.execute(f"SELECT * FROM trips WHERE user_id = ? AND {date_cond} ORDER BY date DESC", (user["id"],)).fetchall()
        expenses = conn.execute(f"SELECT * FROM expenses WHERE user_id = ? AND {date_cond} ORDER BY date DESC", (user["id"],)).fetchall()
        maintenance = conn.execute("SELECT * FROM maintenance WHERE user_id = ? ORDER BY date DESC", (user["id"],)).fetchall()
    data = {
        "export_date": datetime.now().isoformat(),
        "user": user["username"],
        "role": user["role"],
        "trips": [dict(r) for r in trips],
        "expenses": [dict(r) for r in expenses],
        "maintenance": [dict(r) for r in maintenance],
    }
    if format == "json":
        return JSONResponse(content=data, headers={"Content-Disposition": "attachment; filename=driver_data.json"})
    return data

# ── Trends ──
@app.get("/api/trends")
def trends(request: Request, days: int = 90):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    with get_db() as conn:
        weekly = conn.execute(f"""
            SELECT strftime('%Y-W%W', date) as week, COUNT(*) as trips,
                   COALESCE(SUM(fare+tip-commission),0) as net
            FROM trips WHERE user_id = ? AND date >= date('now', 'localtime', ? || ' days')
            GROUP BY week ORDER BY week
        """, (user["id"], f"-{days}")).fetchall()
    return {"weekly": [dict(r) for r in weekly]}

@app.get("/api/check-setup")
def check_setup():
    with get_db() as conn:
        row = conn.execute("SELECT value FROM car_info WHERE key='setup_complete'").fetchone()
    return {"setup_complete": row is not None and row["value"] == "true"}

# ── CSV Upload ──
PLATFORM_COLUMN_MAPS = {
    "uber": {"date":["date","trip date","date/time","start date","trip_date"],
             "fare":["fare","fare amount","trip fare","amount","earnings","driver pay"],
             "tip":["tip","tip amount","tips"],
             "commission":["service fee","service_fee","fee","uber fee","commission","booking fee"],
             "distance":["distance","trip distance","distance (km)","distance (mi)","miles","km"],
             "start_time":["start time","pickup time","start","begin trip","trip start time"],
             "end_time":["end time","dropoff time","end","end trip","trip end time"]},
    "didi": {"date":["date","order date","trip date","date/time","start date"],
             "fare":["fare","fare amount","total fare","amount","income","earnings","driver earnings"],
             "tip":["tip","tip amount","tips","gratuity"],
             "commission":["service fee","commission","platform fee","didi fee","fee"],
             "distance":["distance","trip distance","distance (km)","km"],
             "start_time":["start time","pickup time","start","departure time"],
             "end_time":["end time","dropoff time","end","arrival time"]},
    "indrive": {"date":["date","trip date","order date","date/time"],
                "fare":["fare","amount","price","trip amount","driver amount","earnings"],
                "tip":["tip","tip amount","tips","bonus"],
                "commission":["commission","service fee","fee","indrive fee","platform fee"],
                "distance":["distance","trip distance","distance (km)","km"],
                "start_time":["start time","pickup time","start"],
                "end_time":["end time","dropoff time","end"]}
}

def _find_column(headers, aliases):
    h_lower = [h.strip().lower() for h in headers]
    for alias in aliases:
        al = alias.lower()
        for i, h in enumerate(h_lower):
            if al == h or al in h or h in al:
                return headers[i]
    return None

def _parse_date(val):
    val = val.strip()
    if re.match(r'^\d{4}-\d{2}-\d{2}', val): return val[:10]
    m = re.match(r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})', val)
    if m:
        p1, p2, p3 = m.group(1), m.group(2), m.group(3)
        if int(p1) > 12: return f"{p3}-{p2.zfill(2)}-{p1.zfill(2)}"
        return f"{p3}-{p1.zfill(2)}-{p2.zfill(2)}"
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%d/%m/%Y","%Y/%m/%d","%d-%m-%Y"):
        try: return datetime.strptime(val[:10], fmt).strftime("%Y-%m-%d")
        except: pass
    return date.today().isoformat()

def _parse_time(val):
    val = val.strip()
    m = re.match(r'(\d{1,2}):(\d{2})(?::(\d{2}))?', val)
    if m:
        h, mn = int(m.group(1)), m.group(2)
        if 'pm' in val.lower() and h < 12: h += 12
        elif 'am' in val.lower() and h == 12: h = 0
        return f"{h:02d}:{mn}"
    return ""

def _parse_float(val):
    if not val or not val.strip(): return 0.0
    val = val.strip().replace(',','').replace('$','').replace('€','').replace('ج.م','')
    arabic_map = str.maketrans("٠١٢٣٤٥٦٧٨٩","0123456789")
    try: return float(val.translate(arabic_map))
    except: return 0.0

@app.post("/api/upload-statement")
async def upload_statement(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    form = await request.form()
    platform = form.get("platform","uber")
    if platform not in ("uber","didi","indrive"):
        raise HTTPException(400, "منصة غير معروفة")
    file = form.get("file")
    if not file:
        raise HTTPException(400, "لم يتم رفع ملف")
    content = await file.read()
    try: text = content.decode("utf-8-sig")
    except: text = content.decode("latin-1", errors="replace")

    col_map = PLATFORM_COLUMN_MAPS.get(platform, PLATFORM_COLUMN_MAPS["uber"])
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return {"message": "لم يتم العثور على مشاوير ", "count": 0}
    headers = reader.fieldnames
    date_col = _find_column(headers, col_map["date"])
    fare_col = _find_column(headers, col_map["fare"])
    tip_col = _find_column(headers, col_map["tip"])
    comm_col = _find_column(headers, col_map["commission"])
    dist_col = _find_column(headers, col_map["distance"])
    start_col = _find_column(headers, col_map["start_time"])
    end_col = _find_column(headers, col_map["end_time"])

    inserted = 0; skipped = 0
    with get_db() as conn:
        for row in reader:
            fare = _parse_float(row.get(fare_col or ""))
            if fare <= 0: continue
            d = _parse_date(row.get(date_col or ""))
            tip = _parse_float(row.get(tip_col or "")) if tip_col else 0
            comm = _parse_float(row.get(comm_col or "")) if comm_col else 0
            dist = _parse_float(row.get(dist_col or "")) if dist_col else 0
            st = _parse_time(row.get(start_col or "")) if start_col else ""
            et = _parse_time(row.get(end_col or "")) if end_col else ""
            dup = conn.execute(
                "SELECT id FROM trips WHERE user_id=? AND platform=? AND date=? AND fare=? AND start_time=?",
                (user["id"], platform, d, fare, st)
            ).fetchone()
            if dup: skipped+=1; continue
            conn.execute(
                "INSERT INTO trips (user_id, platform, date, start_time, end_time, fare, tip, commission, distance_km, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (user["id"], platform, d, st, et, fare, tip, comm, dist, f"مستورد من {platform.upper()} ")
            )
            inserted+=1
    return {"message": f" تم استيراد {inserted} مشوار", "inserted": inserted, "skipped": skipped, "total": inserted+skipped}

# ── Connected Accounts ──
@app.get("/api/connected-accounts")
def get_connected_accounts(request: Request):
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        accounts = conn.execute("SELECT * FROM connected_accounts WHERE user_id=? ORDER BY platform", (user["id"],)).fetchall()
    return {"accounts": [dict(a) for a in accounts]}

@app.post("/api/connect-platform/{platform}")
def connect_platform(request: Request, platform: str):
    """Initiate platform connection. Returns redirect to branded OAuth page."""
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    if platform not in ("uber", "didi", "indrive"):
        raise HTTPException(400, "منصة غير معروفة")
    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM connected_accounts WHERE platform = ? AND user_id = ?",
            (platform, user["id"])
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO connected_accounts (user_id, platform, status, token_data, connected_at) "
                "VALUES (?, 'pending', '{}', datetime('now','localtime'))",
                (user["id"], platform)
            )
    return {
        "message": f"فتح اتصال {platform} ",
        "redirect_url": f"/api/oauth/{platform}/authorize"
    }

@app.get("/api/oauth/{platform}/authorize")
def oauth_authorize(request: Request, platform: str, account_id: int = 0):
    """Branded OAuth connect page per platform."""
    if platform not in ("uber", "didi", "indrive"):
        raise HTTPException(400, "منصة غير معروفة")
    tmpl = f"oauth_{platform}.html"
    return render(tmpl, platform=platform, account_id=account_id, request=request)

@app.post("/api/oauth/{platform}/callback")
def oauth_callback(request: Request, platform: str, data: dict):
    """Store API credentials for a connected platform."""
    user = get_current_user(request)
    if not user or not user.get("id"):
        raise HTTPException(401, "يجب تسجيل الدخول أولاً")
    if platform not in ("uber", "didi", "indrive"):
        raise HTTPException(400, "منصة غير معروفة")
    with get_db() as conn:
        # Check if exists — update or insert
        existing = conn.execute(
            "SELECT id FROM connected_accounts WHERE user_id = ? AND platform = ?",
            (user["id"], platform)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE connected_accounts SET status = 'connected', token_data = ?, connected_at = datetime('now','localtime'), last_sync = datetime('now','localtime') WHERE id = ?",
                (json.dumps(data, ensure_ascii=False), existing["id"])
            )
        else:
            conn.execute(
                "INSERT INTO connected_accounts (user_id, platform, status, token_data, connected_at, last_sync) "
                "VALUES (?, ?, 'connected', ?, datetime('now','localtime'), datetime('now','localtime'))",
                (user["id"], platform, json.dumps(data, ensure_ascii=False))
            )
    return {"message": f"تم ربط {platform} "}

# ═══════════════════════════════════════════════════════════════════════════
# ── MAINTENANCE POLICY + COMMISSION COMPARISON ──────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

DRIVER_MAINT_TYPES = ["تغيير زيت", "فرامل"]

@app.get("/api/maintenance-policy")
def maintenance_policy(request: Request):
    """Return the maintenance policy config."""
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}
    return {
        "driver_maintenance_types": DRIVER_MAINT_TYPES,
        "oil_change_free_count": int(info.get("oil_change_free_count", 1)),
        "brake_service_free_count": int(info.get("brake_service_free_count", 1)),
        "oil_change_cost_est": float(info.get("oil_change_cost_est", 350)),
        "brake_service_cost_est": float(info.get("brake_service_cost_est", 600)),
    }

@app.get("/api/commission-comparison")
def commission_comparison(request: Request):
    """Return platform commission data for promotions."""
    user = get_current_user(request)
    if not user: raise HTTPException(401)
    with get_db() as conn:
        info = {r["key"]: r["value"] for r in conn.execute("SELECT * FROM car_info").fetchall()}

    # Count driver's first-time free usage
    driver_data = {}
    if user["role"] == "driver":
        with get_db() as conn:
            oil_done = conn.execute(
                "SELECT COUNT(*) FROM maintenance WHERE user_id=? AND type='تغيير زيت' AND first_time_free=1",
                (user["id"],)
            ).fetchone()[0]
            brake_done = conn.execute(
                "SELECT COUNT(*) FROM maintenance WHERE user_id=? AND type='فرامل' AND first_time_free=1",
                (user["id"],)
            ).fetchone()[0]
            driver_data = {
                "oil_free_used": oil_done,
                "brake_free_used": brake_done,
                "oil_free_total": int(info.get("oil_change_free_count", 1)),
                "brake_free_total": int(info.get("brake_service_free_count", 1)),
            }

    our_split_pct = float(info.get("promo_our_split", 50))
    driver_keeps = our_split_pct
    owner_takes = 100 - our_split_pct

    return {
        "platforms": [
            {"name": "Uber", "commission_pct": float(info.get("promo_uber_commission", 25)), "color": "#06C167", "icon": ""},
            {"name": "Didi", "commission_pct": float(info.get("promo_didi_commission", 20)), "color": "#FF6B35", "icon": ""},
            {"name": "InDrive", "commission_pct": float(info.get("promo_indrive_commission", 15)), "color": "#E53935", "icon": ""},
        ],
        "our_offer": {
            "commission_pct": float(info.get("promo_our_commission", 0)),
            "driver_keeps_pct": driver_keeps,
            "owner_takes_pct": owner_takes,
            "promo_banner": info.get("promo_banner", "حلل أرباحك عبر كل المنصات في مكان واحد"),
        },
        "driver_data": driver_data,
    }

# ── Seed Demo ──
@app.post("/api/seed-demo")
def seed_demo(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    import random
    with get_db() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM trips WHERE user_id=?", (user["id"],)).fetchone()[0]
        if existing > 5:
            return {"message": "عندك مشاوير كده "}
        platforms = ["uber","didi","indrive","personal"]
        for days_ago in range(30):
            d = (date.today() - timedelta(days=days_ago)).isoformat()
            for _ in range(random.randint(0,4)):
                plat = random.choice(platforms)
                fare = round(random.uniform(30,250),2)
                if plat=="uber": fare*=1.1; comm=fare*0.25
                elif plat=="didi": comm=fare*0.20
                elif plat=="indrive": comm=fare*0.15
                else: comm=0
                tip = round(random.uniform(0,20),2) if plat!="personal" else 0
                h,m = random.randint(8,22), random.randint(0,50)
                dur = random.randint(15,90)
                st = f"{h:02d}:{m:02d}"
                et = (datetime(2000,1,1,h,m)+timedelta(minutes=dur)).strftime("%H:%M")
                conn.execute(
                    "INSERT INTO trips (user_id, platform, date, start_time, end_time, fare, tip, commission, distance_km, notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (user["id"], plat, d, st, et, fare, tip, comm, round(random.uniform(3,35),1), "بيانات تجريبية")
                )
        conn.execute(
            "INSERT INTO expenses (user_id, category, subcategory, amount, date) VALUES (?, 'بنزين', 'وقود', ?, ?)",
            (user["id"], round(random.uniform(200,500),2), (date.today()-timedelta(days=random.randint(0,5))).isoformat())
        )
    return {"message": "تمت إضافة بيانات تجريبية  (30 يوم)"}

# ── Language API ──

@app.post("/api/set-lang")
def set_lang(data: dict):
    lang = data.get("lang", "ar")
    if lang not in ("ar", "en"):
        lang = "ar"
    resp = JSONResponse({"message": f"Language set to {lang}"})
    resp.set_cookie(key=LANG_COOKIE, value=lang, max_age=365*24*3600, httponly=True, samesite="lax")
    return resp

@app.post("/api/upload-csv")
def upload_csv(request: Request, data: dict):
    """Upload CSV text for a platform and parse trips."""
    user = get_current_user(request)
    if not user:
        raise HTTPException(401)
    platform = data.get("platform", "uber")
    content = data.get("csv", "")
    if not content.strip():
        raise HTTPException(400, "CSV content is empty")
    import csv, io
    reader = csv.DictReader(io.StringIO(content))
    count = 0
    for row in reader:
        try:
            date = row.get("date") or row.get("Date") or row.get("التاريخ") or ""
            fare = float(row.get("fare") or row.get("Fare") or row.get("Amount") or row.get("المبلغ") or 0)
            tip = float(row.get("tip") or row.get("Tip") or 0)
            comm = float(row.get("commission") or row.get("Commission") or 0)
            dist = float(row.get("distance_km") or row.get("Distance") or row.get("المسافة") or 0)
            if not date or fare <= 0: continue
            c = get_db().execute(
                "SELECT id FROM trips WHERE user_id=? AND date=? AND fare=? AND platform=?",
                (user["id"], date, fare, platform)
            ).fetchone()
            if c: continue
            get_db().execute(
                "INSERT INTO trips (user_id, platform, date, fare, tip, commission, distance_km, notes) VALUES (?,?,?,?,?,?,?,?)",
                (user["id"], platform, date, fare, tip, comm, dist, f"CSV import from {platform}")
            )
            count += 1
        except Exception as e:
            print(f"CSV row error: {e}")
            continue
    get_db().commit()
    existing = get_db().execute(
        "SELECT id FROM connected_accounts WHERE user_id=? AND platform=?", (user["id"], platform)
    ).fetchone()
    if existing:
        get_db().execute("UPDATE connected_accounts SET status='connected', last_sync=datetime('now','localtime') WHERE id=?", (existing["id"],))
    else:
        get_db().execute(
            "INSERT INTO connected_accounts (user_id, platform, status, auth_type, token_data) VALUES (?,?,'connected','csv',?)",
            (user["id"], platform, f"CSV import: {count} trips")
        )
    get_db().commit()
    return {"message": f"Imported {count} trips", "count": count}

# ═══════════════════════════════════════════════════════════════════════════
# ── PAGES ─────────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/")
    return render("login.html", request=request)

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/")
    with get_db() as conn:
        count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    return render("register.html", request=request, has_owner=(count>0))

@app.get("/register/uber", response_class=HTMLResponse)
def register_uber_page(request: Request):
    return render("register_uber.html", request=request)

@app.get("/register/didi", response_class=HTMLResponse)
def register_didi_page(request: Request):
    return render("register_didi.html", request=request)

@app.get("/register/indrive", response_class=HTMLResponse)
def register_indrive_page(request: Request):
    return render("register_indrive.html", request=request)

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Redirect based on role."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    if user["role"] == "owner":
        # Owner: check if setup complete → owner dashboard
        with get_db() as conn:
            setup_row = conn.execute("SELECT value FROM car_info WHERE key='setup_complete'").fetchone()
        if setup_row is None or setup_row["value"] != "true":
            return RedirectResponse(url="/setup")
        return RedirectResponse(url="/owner-dashboard")
    else:
        # Driver: go to connect page
        return RedirectResponse(url="/driver-connect")

@app.get("/setup", response_class=HTMLResponse)
def setup_page(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    return render("setup.html", request=request, current_step=1, user=user)

@app.get("/owner-dashboard", response_class=HTMLResponse)
def owner_dashboard_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        return RedirectResponse(url="/login")
    return render("owner_dashboard.html", request=request, user=user)

@app.get("/driver-dashboard", response_class=HTMLResponse)
def driver_dashboard_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "driver":
        return RedirectResponse(url="/login")
    return render("driver_dashboard.html", request=request, user=user)

@app.get("/driver-connect", response_class=HTMLResponse)
def driver_connect_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "driver":
        return RedirectResponse(url="/login")
    return render("driver_connect.html", request=request, user=user)

@app.get("/trips", response_class=HTMLResponse)
def trips_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("trips.html", request=request, user=user)

@app.get("/expenses", response_class=HTMLResponse)
def expenses_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("expenses.html", request=request, user=user)

@app.get("/maintenance", response_class=HTMLResponse)
def maintenance_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("maintenance.html", request=request, user=user)

@app.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("settings.html", request=request, user=user)

@app.get("/reports", response_class=HTMLResponse)
def reports_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("reports.html", request=request, user=user)

@app.get("/accounts", response_class=HTMLResponse)
def accounts_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("accounts.html", request=request, user=user)

@app.get("/fuel", response_class=HTMLResponse)
def fuel_page(request: Request):
    user = get_current_user(request)
    if not user: return RedirectResponse(url="/login")
    return render("fuel.html", request=request, user=user)

@app.get("/verify", response_class=HTMLResponse)
def verify_page(request: Request):
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        return RedirectResponse(url="/login")
    return render("verify.html", request=request, user=user)

@app.get("/drivers", response_class=HTMLResponse)
def drivers_page(request: Request):
    """Owner sees all drivers."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        return RedirectResponse(url="/login")
    return render("drivers.html", request=request, user=user)

@app.get("/revenue", response_class=HTMLResponse)
def revenue_page(request: Request):
    """Driver sees revenue breakdown by platform."""
    user = get_current_user(request)
    if not user or user["role"] != "driver":
        return RedirectResponse(url="/login")
    return render("revenue.html", request=request, user=user)

@app.get("/cars", response_class=HTMLResponse)
def cars_page(request: Request):
    """Owner sees all cars."""
    user = get_current_user(request)
    if not user or user["role"] != "owner":
        return RedirectResponse(url="/login")
    return render("cars.html", request=request, user=user)

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000)
