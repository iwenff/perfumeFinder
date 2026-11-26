import json
import sqlite3
import time
from contextlib import closing, contextmanager


class Repository:
    def __init__(self, path):
        self.path = path
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS channels (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS added_channels (
                    id INTEGER PRIMARY KEY, title TEXT NOT NULL, username TEXT, access_hash INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS public_channels (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, title TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, volume REAL, days INTEGER NOT NULL,
                    created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY, created REAL NOT NULL, payload TEXT NOT NULL
                );
            """)

    @contextmanager
    def connect(self):
        with closing(sqlite3.connect(self.path)) as db, db:
            yield db

    def add_channel(self, channel):
        with self.connect() as db:
            db.execute("REPLACE INTO added_channels VALUES (?, ?, ?, ?)",
                       (channel.id, channel.title, channel.username, channel.peer.access_hash))
            db.execute("INSERT INTO channels VALUES (?, ?, 1) ON CONFLICT(id) DO UPDATE SET enabled=1, title=excluded.title",
                       (channel.id, channel.title))

    def add_public_channel(self, username, title):
        with self.connect() as db:
            row = db.execute("""
                INSERT INTO public_channels(username, title) VALUES (?, ?)
                ON CONFLICT(username) DO UPDATE SET title=excluded.title
                RETURNING -id, username, title
            """, (username, title)).fetchone()
            db.execute("INSERT INTO channels VALUES (?, ?, 1) ON CONFLICT(id) DO UPDATE SET enabled=1, title=excluded.title",
                       (row[0], title))
        return row

    def public_channels(self):
        with self.connect() as db:
            return db.execute("SELECT -id, username, title FROM public_channels").fetchall()

    def added_channels(self):
        with self.connect() as db:
            return db.execute("SELECT id, title, username, access_hash FROM added_channels").fetchall()

    def channels(self):
        with self.connect() as db:
            return {row[0]: bool(row[1]) for row in db.execute("SELECT id, enabled FROM channels")}

    def sync_channels(self, channels):
        with self.connect() as db:
            db.executemany("""
                INSERT INTO channels(id, title) VALUES (?, ?)
                ON CONFLICT(id) DO UPDATE SET title=excluded.title
            """, [(channel.id, channel.title) for channel in channels])

    def toggle(self, channel_id):
        with self.connect() as db:
            db.execute("UPDATE channels SET enabled=1-enabled WHERE id=?", (channel_id,))

    def days(self):
        with self.connect() as db:
            row = db.execute("SELECT value FROM settings WHERE key='days'").fetchone()
        return row[0] if row else 30

    def set_days(self, days):
        with self.connect() as db:
            db.execute("REPLACE INTO settings VALUES ('days', ?)", (days,))

    def record(self, name, volume, days):
        with self.connect() as db:
            db.execute("INSERT INTO history(name, volume, days, created) VALUES (?, ?, ?, ?)",
                       (name, volume, days, time.time()))

    def history(self, limit=10, offset=0):
        with self.connect() as db:
            return db.execute("SELECT id, name, volume, days FROM history ORDER BY id DESC LIMIT ? OFFSET ?",
                              (limit, offset)).fetchall()

    def previous(self, item):
        with self.connect() as db:
            return db.execute("SELECT name, volume, days FROM history WHERE id=?", (item,)).fetchone()

    def cached(self, key):
        with self.connect() as db:
            db.execute("DELETE FROM cache WHERE created <= ?", (time.time() - 300,))
            row = db.execute("SELECT payload FROM cache WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def store(self, key, payload):
        with self.connect() as db:
            db.execute("REPLACE INTO cache VALUES (?, ?, ?)", (key, time.time(), json.dumps(payload)))
