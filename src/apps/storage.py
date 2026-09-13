"""Local durable application store. BEGIN IMMEDIATE serializes local workers.

This deliberately uses SQLite for synthetic demonstrations, not AWS storage.
All task acceptance and outbox writes share a transaction.
"""
from contextlib import contextmanager
import json
import sqlite3
from uuid import uuid4


def reference(prefix):
    return f"{prefix}_{uuid4().hex}"


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


class Store:
    def __init__(self, path):
        self.path = path
        with self.transaction() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS help_sessions (
                    request_id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, token_hash TEXT UNIQUE NOT NULL,
                    conversation TEXT NOT NULL, result TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY, owner TEXT NOT NULL, state TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, conversation TEXT NOT NULL, request_key TEXT NOT NULL,
                    payload TEXT NOT NULL, status TEXT NOT NULL, result TEXT,
                    UNIQUE(conversation, request_key));
                CREATE TABLE IF NOT EXISTS outbox (
                    task TEXT PRIMARY KEY, delivered INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, conversation TEXT NOT NULL UNIQUE,
                    payload_hash TEXT NOT NULL, status TEXT NOT NULL, receipt TEXT, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (
                    id TEXT PRIMARY KEY, conversation TEXT NOT NULL, kind TEXT NOT NULL,
                    version INTEGER NOT NULL, status TEXT NOT NULL, proposal TEXT NOT NULL,
                    UNIQUE(conversation, kind));
                CREATE TABLE IF NOT EXISTS decisions (
                    id TEXT PRIMARY KEY, review TEXT NOT NULL, reviewer TEXT NOT NULL,
                    payload TEXT NOT NULL, result TEXT NOT NULL);
            ''')

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()
