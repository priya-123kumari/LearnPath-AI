"""Data access for the backend tier. The only module that talks to the database (SQLite file built by database/load_db.py)."""
import json
import os
import sqlite3
import threading
import pandas as pd
from .config import DB_PATH
from .engine import Catalog

_local = threading.local()
_catalog = {"db": None, "cat": None}


def db_path():
    return os.environ.get("LEARNPATH_DB", DB_PATH)


def conn():
    path = db_path()
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != path:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Database not found at {path}. Build it: python -m database.load_db --data database/data/starter")
        c = sqlite3.connect(path, check_same_thread=False)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys = ON")
        _local.conn, _local.path = c, path
    return c


def rows(sql, params=()):
    return [dict(r) for r in conn().execute(sql, params).fetchall()]


def one(sql, params=()):
    r = conn().execute(sql, params).fetchone()
    return dict(r) if r else None


def scalar(sql, params=()):
    r = conn().execute(sql, params).fetchone()
    return r[0] if r else None


def report(name):
    v = scalar("SELECT body FROM audit_report WHERE name = ?", (name,))
    return json.loads(v) if v else None


def catalog():
    """Skill graph + content catalogue, cached per database file (master data only changes on reload)."""
    if _catalog["db"] != db_path() or _catalog["cat"] is None:
        c = conn()
        T = {name: pd.read_sql(f"SELECT * FROM {table}", c) for name, table in
             (("Skill", "skills"), ("SkillPrerequisite", "skill_prerequisites"), ("ContentItem", "content_items"), ("ContentSkill", "content_skills"))}
        T["SkillPrerequisite"]["effective_to"] = T["SkillPrerequisite"]["effective_to"].fillna("")
        _catalog.update(db=db_path(), cat=Catalog.from_tables(T))
    return _catalog["cat"]


def reset_cache():
    _catalog.update(db=None, cat=None)
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
    _local.conn = None
