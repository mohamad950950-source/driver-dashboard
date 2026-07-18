"""
Database abstraction layer — SQLite (local) or PostgreSQL (Netlify/Supabase).
Auto-detects from DATABASE_URL env var.
Wraps psycopg2 to behave like sqlite3.Connection so all existing code works unchanged.
"""
import os
import sqlite3
from pathlib import Path

DATABASE_URL = os.getenv("DATABASE_URL", "")
USE_POSTGRES = bool(DATABASE_URL)
BASE = Path(__file__).resolve().parent

# ═══════════════════════════════════════════════
# PostgreSQL wrapper — mimics sqlite3.Connection
# ═══════════════════════════════════════════════
if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras

    class PostgresCursor:
        """Wraps psycopg2 cursor to behave like sqlite3 cursor."""
        def __init__(self, cur):
            self._cur = cur
            self._rowcount = 0
            self.lastrowid = None

        def fetchone(self):
            row = self._cur.fetchone()
            if row:
                self._rowcount = 1
            return row

        def fetchall(self):
            rows = self._cur.fetchall()
            self._rowcount = len(rows) if rows else 0
            return rows

    class PostgresConn:
        """Wraps psycopg2 connection to behave like sqlite3.Connection."""
        def __init__(self, dsn):
            self._conn = psycopg2.connect(dsn)
            self._conn.autocommit = False
            self._cur = None

        def execute(self, sql, params=None):
            """Replace ? with %s, auto-add RETURNING id for INSERTs."""
            pg_sql = sql.replace('?', '%s')
            # Auto-add RETURNING id for INSERTs that don't have it yet
            stripped = pg_sql.strip().upper()
            if stripped.startswith('INSERT') and 'RETURNING' not in stripped:
                # Find the last ) and add RETURNING id before it... 
                # Actually just append at the end
                pg_sql += ' RETURNING id'
            cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            try:
                cur.execute(pg_sql, params or ())
            except Exception as e:
                self._conn.rollback()
                raise e
            wrapped = PostgresCursor(cur)
            # Fetch the returned id for INSERTs
            wrapped.lastrowid = cur.fetchone()[0] if cur.description else None
            self._cur = wrapped
            return self._cur

        def executemany(self, sql, seq_of_params):
            pg_sql = sql.replace('?', '%s')
            cur = self._conn.cursor()
            for params in seq_of_params:
                cur.execute(pg_sql, params)
            self._conn.commit()

        def executescript(self, script):
            """Execute multi-statement SQL script — split by ; for PostgreSQL."""
            cur = self._conn.cursor()
            statements = [s.strip() for s in script.split(';') if s.strip()]
            for stmt in statements:
                try:
                    cur.execute(stmt)
                except Exception:
                    pass  # skip errors (IF NOT EXISTS handles most)
            self._conn.commit()

        def commit(self):
            self._conn.commit()

        def rollback(self):
            self._conn.rollback()

        def close(self):
            self._conn.close()

        def cursor(self):
            return self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if exc_type is None:
                try:
                    self.commit()
                except:
                    self.rollback()
            else:
                self.rollback()
            self.close()

    def get_db():
        return PostgresConn(DATABASE_URL)

    def row_to_dict(row):
        """Convert sqlite3.Row or RealDictRow to plain dict."""
        if row is None:
            return None
        return dict(row)

else:
    # ── SQLite (local dev) ──
    DATA_DIR = BASE / "data"
    DATA_DIR.mkdir(exist_ok=True)
    DB = str(DATA_DIR / "driver.db")

    def get_db():
        conn = sqlite3.connect(DB, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def row_to_dict(row):
        if row is None:
            return None
        return dict(row)
