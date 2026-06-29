from __future__ import annotations

import sqlite3
from pathlib import Path

from jobpipe.storage.migrations import apply_migrations, get_schema_version
from jobpipe.storage.connection_pool import SQLiteConnectionPool, PooledConnection

# Global connection pool instance
_pool: SQLiteConnectionPool | None = None
_pool_lock = None  # Lazy import to avoid circular


def _get_pool(db_path: Path, max_connections: int = 15, wait_timeout: float = 30.0) -> SQLiteConnectionPool:
    """Get or create the global connection pool."""
    global _pool
    
    if _pool is None:
        from threading import Lock
        global _pool_lock
        if _pool_lock is None:
            _pool_lock = Lock()
        
        with _pool_lock:
            if _pool is None:
                _pool = SQLiteConnectionPool(
                    db_path, max_connections=max_connections, wait_timeout=wait_timeout
                )
    elif _pool._db_path != db_path:
        # Database path changed, recreate pool
        _pool.close_all()
        _pool = SQLiteConnectionPool(
            db_path, max_connections=max_connections, wait_timeout=wait_timeout
        )
    else:
        # Pool exists for the same db_path — grow max_connections if caller
        # requests more than the pool was originally created with.
        if max_connections > _pool._max_connections:
            with _pool._lock:
                _pool._max_connections = max_connections
        if wait_timeout > _pool._wait_timeout:
            with _pool._lock:
                _pool._wait_timeout = wait_timeout
    
    return _pool


def connect(db_path: Path) -> sqlite3.Connection | PooledConnection:
    """
    Get a pooled connection context manager.
    
    Usage:
        with connect(db_path) as conn:
            conn.execute(...)
    
    Returns a PooledConnection that automatically returns the connection to the pool.
    """
    pool = _get_pool(db_path)
    return PooledConnection(pool)


def get_pool_status(db_path: Path) -> dict | None:
    """Get current connection pool status for monitoring.
    
    Returns:
        Dictionary with pool status (created, available, max, in_use) or None if no pool exists.
    """
    global _pool
    if _pool is not None and _pool._db_path == db_path:
        return _pool.get_status()
    return None


def initialize_database(db_path: Path) -> None:
    """Initialize the database with migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)

    # Use a direct connection for initialization (not pooled)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA journal_mode=WAL;")
        
        apply_migrations(conn)
        conn.commit()
    finally:
        conn.close()


def schema_version(db_path: Path) -> int:
    """Get the current schema version."""
    with connect(db_path) as conn:
        return get_schema_version(conn)


def close_connection_pool() -> None:
    """Close all connections in the pool. Call on application shutdown."""
    global _pool
    if _pool is not None:
        _pool.close_all()
        _pool = None
