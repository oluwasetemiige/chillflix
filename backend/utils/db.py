"""Database access for PostgreSQL / Supabase, with a SQLite fallback for local dev.

Write SQL with `?` placeholders. They are converted to `%s` for PostgreSQL.

    db.query("SELECT * FROM movies WHERE id = ?", [1])   -> list of dicts
    db.one(...)                                          -> dict or None
    db.execute(...)                                      -> rows affected
    db.insert("INSERT INTO ...", params)                 -> new id
    with db.tx() as t:  t.execute(...); t.insert(...)    -> all-or-nothing

The schema lives in database/schema.sql (single source of truth). For SQLite it
is translated on the fly by `_to_sqlite`.
"""
import re
import sqlite3
import threading
from contextlib import contextmanager

from config import BASE_DIR, Config

SCHEMA_FILE = BASE_DIR.parent / "database" / "schema.sql"


def _to_sqlite(sql):
    """Translate schema.sql (PostgreSQL) into SQLite syntax."""
    sql = sql.split("-- ===== SUPABASE")[0]
    sql = sql.replace("BIGSERIAL PRIMARY KEY", "INTEGER PRIMARY KEY AUTOINCREMENT")
    sql = sql.replace("DEFAULT NOW()", "DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00','now'))")
    sql = sql.replace("DEFAULT TRUE", "DEFAULT 1").replace("DEFAULT FALSE", "DEFAULT 0")
    for pg, lite in (("TIMESTAMPTZ", "TEXT"), ("DOUBLE PRECISION", "REAL"), ("BIGINT", "INTEGER"), ("BOOLEAN", "INTEGER")):
        sql = sql.replace(pg, lite)
    sql = re.sub(r"\bDATE\b", "TEXT", sql)
    return sql


class _Tx:
    def __init__(self, db, conn):
        self.db = db
        self.conn = conn

    def _prep(self, sql):
        return sql.replace("?", "%s") if self.db.is_postgres else sql

    def _cursor(self):
        if self.db.is_postgres:
            from psycopg2.extras import RealDictCursor
            return self.conn.cursor(cursor_factory=RealDictCursor)
        return self.conn.cursor()

    def query(self, sql, params=()):
        cur = self._cursor()
        try:
            cur.execute(self._prep(sql), list(params))
            return [dict(r) for r in cur.fetchall()]
        finally:
            cur.close()

    def one(self, sql, params=()):
        rows = self.query(sql, params)
        return rows[0] if rows else None

    def execute(self, sql, params=()):
        cur = self._cursor()
        try:
            cur.execute(self._prep(sql), list(params))
            return cur.rowcount
        finally:
            cur.close()

    def insert(self, sql, params=()):
        cur = self._cursor()
        try:
            cur.execute(self._prep(sql) + " RETURNING id", list(params))
            row = cur.fetchone()
            return dict(row)["id"] if row is not None else None
        finally:
            cur.close()

    def script(self, sql):
        if self.db.is_postgres:
            cur = self._cursor()
            cur.execute(sql)
            cur.close()
        else:
            self.conn.executescript(sql)


class Database:
    def __init__(self, url):
        self.url = url
        self.is_postgres = url.startswith(("postgres://", "postgresql://"))
        self._pool = None
        self._lock = threading.Lock()
        if not self.is_postgres:
            self.sqlite_path = url.replace("sqlite:///", "", 1)

    # -- connections -------------------------------------------------------
    def _get_pool(self):
        with self._lock:
            if self._pool is None:
                from psycopg2.pool import ThreadedConnectionPool
                dsn = self.url.replace("postgres://", "postgresql://", 1)
                self._pool = ThreadedConnectionPool(1, 10, dsn, connect_timeout=10)
            return self._pool

    def _acquire(self):
        if self.is_postgres:
            return self._get_pool().getconn()
        conn = sqlite3.connect(self.sqlite_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _release(self, conn):
        if self.is_postgres:
            self._get_pool().putconn(conn, close=bool(conn.closed))
        else:
            conn.close()

    @contextmanager
    def tx(self):
        conn = self._acquire()
        try:
            yield _Tx(self, conn)
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise
        finally:
            self._release(conn)

    # -- shortcuts (each runs in its own transaction) ----------------------------
    def query(self, sql, params=()):
        with self.tx() as t:
            return t.query(sql, params)

    def one(self, sql, params=()):
        with self.tx() as t:
            return t.one(sql, params)

    def execute(self, sql, params=()):
        with self.tx() as t:
            return t.execute(sql, params)

    def insert(self, sql, params=()):
        with self.tx() as t:
            return t.insert(sql, params)

    # -- housekeeping ----------------------------------------------------------
    def ping(self):
        self.one("SELECT 1 AS ok")
        return True

    def init_schema(self):
        sql = SCHEMA_FILE.read_text(encoding="utf-8")
        if not self.is_postgres:
            sql = _to_sqlite(sql)
        with self.tx() as t:
            t.script(sql)


db = Database(Config.DATABASE_URL)
