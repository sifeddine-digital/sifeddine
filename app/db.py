import json
import sqlite3

from flask import current_app, g

from .referentiel import SEUIL_BLOC_DEFAUT, SEUIL_GLOBAL_DEFAUT

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    phone TEXT DEFAULT '',
    role TEXT NOT NULL CHECK (role IN ('admin', 'superviseur')),
    password_hash TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_login TEXT
);
CREATE TABLE IF NOT EXISTS stations (
    id INTEGER PRIMARY KEY,
    ship_to TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    secteur TEXT NOT NULL,
    territoire TEXT NOT NULL DEFAULT '',
    supervisor_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    active INTEGER NOT NULL DEFAULT 1,
    sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS checklists (
    id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    week_start TEXT NOT NULL,
    visit_date TEXT,
    data TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'brouillon' CHECK (status IN ('brouillon', 'envoye')),
    score_global REAL,
    statut TEXT DEFAULT '',
    locked INTEGER NOT NULL DEFAULT 0,
    lat REAL, lng REAL,
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    submitted_at TEXT,
    UNIQUE (station_id, week_start)
);
CREATE TABLE IF NOT EXISTS inventaires (
    id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    statut TEXT DEFAULT '',
    baie TEXT DEFAULT '',
    shsc TEXT DEFAULT '',
    items TEXT NOT NULL DEFAULT '{}',
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (station_id, month)
);
CREATE TABLE IF NOT EXISTS stocks (
    id INTEGER PRIMARY KEY,
    station_id INTEGER NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    month TEXT NOT NULL,
    fiable TEXT DEFAULT '',
    methode TEXT DEFAULT '',
    date_inventaire TEXT DEFAULT '',
    frequence TEXT DEFAULT '',
    stock_physique REAL,
    stock_systeme REAL,
    commentaire TEXT DEFAULT '',
    updated_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (station_id, month)
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_checklists_week ON checklists(week_start);
CREATE INDEX IF NOT EXISTS idx_stations_sup ON stations(supervisor_id);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    db.execute("PRAGMA journal_mode = WAL")
    db.commit()


def query(sql, args=(), one=False):
    rows = get_db().execute(sql, args).fetchall()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur


def get_setting(key, default):
    row = query("SELECT value FROM settings WHERE key = ?", (key,), one=True)
    return json.loads(row["value"]) if row else default


def set_setting(key, value):
    execute("INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, json.dumps(value)))


def seuils():
    return (get_setting("seuil_bloc", SEUIL_BLOC_DEFAUT),
            get_setting("seuil_global", SEUIL_GLOBAL_DEFAUT))


def secteurs():
    return [r["secteur"] for r in query("SELECT DISTINCT secteur FROM stations ORDER BY secteur")]
