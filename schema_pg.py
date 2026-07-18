"""
PostgreSQL schema initialization for Supabase/Netlify deployment.
"""
from db import USE_POSTGRES

POSTGRES_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'driver' CHECK(role IN ('owner','driver')),
    phone TEXT DEFAULT '',
    driver_split_pct DOUBLE PRECISION DEFAULT 50,
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
    driver_of_owner INTEGER DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sessions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    token TEXT UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS trips (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    platform TEXT NOT NULL CHECK(platform IN ('uber','didi','indrive','personal')),
    date TEXT NOT NULL,
    start_time TEXT,
    end_time TEXT,
    fare DOUBLE PRECISION NOT NULL DEFAULT 0,
    tip DOUBLE PRECISION NOT NULL DEFAULT 0,
    commission DOUBLE PRECISION NOT NULL DEFAULT 0,
    distance_km DOUBLE PRECISION DEFAULT 0,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fuel_fills (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    odometer_km INTEGER DEFAULT 0,
    liters DOUBLE PRECISION DEFAULT 0,
    total_cost DOUBLE PRECISION DEFAULT 0,
    cost_per_liter DOUBLE PRECISION DEFAULT 0,
    notes TEXT DEFAULT '',
    photo_url TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS expenses (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    category TEXT NOT NULL,
    subcategory TEXT,
    amount DOUBLE PRECISION NOT NULL,
    date TEXT NOT NULL,
    notes TEXT,
    receipt_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS location_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    lat DOUBLE PRECISION NOT NULL,
    lng DOUBLE PRECISION NOT NULL,
    accuracy DOUBLE PRECISION DEFAULT 0,
    source TEXT DEFAULT '',
    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS maintenance (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    date TEXT NOT NULL,
    type TEXT NOT NULL,
    description TEXT,
    cost DOUBLE PRECISION NOT NULL,
    borne_by TEXT NOT NULL DEFAULT 'owner' CHECK(borne_by IN ('driver','owner')),
    first_time_free INTEGER NOT NULL DEFAULT 0,
    odometer_km INTEGER,
    shop_name TEXT,
    next_service_km INTEGER,
    next_service_date TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS car_info (
    id SERIAL PRIMARY KEY,
    key TEXT UNIQUE NOT NULL,
    value TEXT
);

CREATE TABLE IF NOT EXISTS connected_accounts (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL DEFAULT 0,
    platform TEXT NOT NULL CHECK(platform IN ('uber','didi','indrive')),
    status TEXT NOT NULL DEFAULT 'pending',
    auth_type TEXT NOT NULL DEFAULT 'oauth',
    token_data TEXT DEFAULT '{}',
    connected_at TEXT,
    last_sync TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS cars (
    id SERIAL PRIMARY KEY,
    owner_id INTEGER NOT NULL DEFAULT 0 REFERENCES users(id),
    driver_id INTEGER DEFAULT NULL REFERENCES users(id),
    car_name TEXT DEFAULT '',
    plate_number TEXT DEFAULT '',
    fuel_type TEXT DEFAULT 'بنزين 95',
    fuel_cost_per_liter DOUBLE PRECISION DEFAULT 24,
    km_per_liter DOUBLE PRECISION DEFAULT 12,
    driver_split_pct DOUBLE PRECISION DEFAULT 50,
    partner_share_pct DOUBLE PRECISION DEFAULT 50,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS otp_codes (
    id SERIAL PRIMARY KEY,
    phone TEXT NOT NULL,
    code TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);

-- Seed data
INSERT INTO car_info (key, value) VALUES
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
    ('promo_banner', 'حلل أرباحك عبر كل المنصات في مكان واحد')
ON CONFLICT (key) DO NOTHING;
"""


def init_db_pg():
    """Initialize PostgreSQL schema."""
    from db import get_db
    with get_db() as conn:
        cur = conn.cursor()
        # Split by ; and execute each statement
        for stmt in POSTGRES_SCHEMA.split(';'):
            stmt = stmt.strip()
            if stmt:
                try:
                    cur.execute(stmt)
                except Exception as e:
                    # Ignore "already exists" errors
                    if 'already exists' not in str(e).lower():
                        print(f"Schema init warning (non-fatal): {e}")
        conn.commit()
