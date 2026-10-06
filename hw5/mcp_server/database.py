"""Shop-data access stays in MCP. Shared locking coordinates reads with reset/writes."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import sqlite3
from typing import Any

DATABASE_PATH = Path(__file__).resolve().parents[1] / 'data' / 'campus_customs_new.db'


def original_path():
    return DATABASE_PATH.with_name('campus_customs.db')


def protect_original():
    original = original_path()
    if DATABASE_PATH.is_symlink() or DATABASE_PATH.resolve() == original.resolve() or (
        DATABASE_PATH.exists() and original.exists() and DATABASE_PATH.samefile(original)
    ):
        raise RuntimeError('Working database must not alias the original database')


@contextmanager
def shop_lock(exclusive=False):
    protect_original()
    with DATABASE_PATH.with_suffix('.lock').open('a+b') as handle:
        fcntl.flock(handle, fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


@contextmanager
def read_connection():
    with shop_lock():
        connection = sqlite3.connect(DATABASE_PATH.resolve().as_uri()+'?mode=ro', uri=True)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute('PRAGMA query_only=ON')
            connection.execute('BEGIN')
            yield connection
        finally:
            connection.close()


def fetch_one(query: str, parameters: tuple) -> dict[str, Any]:
    with read_connection() as connection:
        row = connection.execute(query, parameters).fetchone()
    if row is None:
        return {'found': False, 'record': None, 'message': 'No matching record found.'}
    return {'found': True, 'record': dict(row)}


def fetch_page(query: str, parameters: tuple, limit: int) -> dict:
    if isinstance(limit, bool) or not 1 <= limit <= 25:
        raise ValueError('limit must be between 1 and 25')
    with read_connection() as connection:
        rows = connection.execute(query+' LIMIT ?', (*parameters, limit+1)).fetchall()
    return {'records': [dict(row) for row in rows[:limit]], 'truncated': len(rows)>limit}
