"""
SQLite connection pool for improved performance.
Reuses connections to avoid the overhead of creating new connections for each operation.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from collections import deque
from pathlib import Path
from threading import Lock

LOGGER = logging.getLogger(__name__)


class SQLiteConnectionPool:
    """
    Thread-safe connection pool for SQLite databases.
    
    Features:
    - Reuses connections to minimize connection overhead
    - Thread-safe with locking
    - Automatic connection cleanup
    - WAL mode enabled for better concurrent read performance
    """
    
    def __init__(self, db_path: Path, max_connections: int = 15, wait_timeout: float = 30.0):
        self._db_path = db_path
        self._max_connections = max_connections
        self._pool: deque[sqlite3.Connection] = deque()
        self._lock = Lock()
        self._created = 0
        self._wait_timeout = wait_timeout  # seconds to wait for available connection
        
    def get_connection(self, timeout: float | None = None) -> sqlite3.Connection:
        """Get a connection from the pool or create a new one.
        
        Args:
            timeout: Maximum seconds to wait for available connection.
                     Defaults to self._wait_timeout.
        
        Raises:
            RuntimeError: If pool is exhausted and timeout expires.
        """
        import time
        
        timeout = timeout if timeout is not None else self._wait_timeout
        deadline = time.time() + timeout
        retry_delay = 0.1  # Start with 100ms, exponential backoff
        max_retry_delay = 2.0  # Cap at 2 seconds
        
        while True:
            with self._lock:
                if self._pool:
                    conn = self._pool.popleft()
                    try:
                        # Verify connection is still valid
                        conn.execute("SELECT 1")
                        return conn
                    except sqlite3.Error:
                        # Connection is bad, create a new one
                        self._created -= 1
                        LOGGER.debug("Pool: removed bad connection, created=%d", self._created)
                
                # Create new connection if under limit
                if self._created < self._max_connections:
                    conn = self._create_connection()
                    self._created += 1
                    LOGGER.debug("Pool: created new connection, created=%d/%d", self._created, self._max_connections)
                    return conn
            
            # Pool exhausted, wait with exponential backoff
            if time.time() >= deadline:
                LOGGER.error(
                    "Pool exhausted: created=%d, max=%d, available=%d, thread=%s",
                    self._created,
                    self._max_connections,
                    len(self._pool),
                    threading.current_thread().name,
                )
                raise RuntimeError(
                    f"Connection pool exhausted after {timeout}s wait. "
                    f"Created: {self._created}, Max: {self._max_connections}"
                )
            
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 1.5, max_retry_delay)  # Exponential backoff
    
    def return_connection(self, conn: sqlite3.Connection) -> None:
        """Return a connection to the pool."""
        with self._lock:
            try:
                # Verify connection is still valid before returning
                conn.execute("SELECT 1")
                if len(self._pool) < self._max_connections:
                    self._pool.append(conn)
                    LOGGER.debug("Pool: returned connection, available=%d/%d", len(self._pool), self._max_connections)
                else:
                    conn.close()
                    self._created -= 1
                    LOGGER.debug("Pool: closed excess connection, created=%d", self._created)
            except sqlite3.Error:
                # Connection is bad, don't return it
                try:
                    conn.close()
                except Exception:
                    pass
                self._created -= 1
                LOGGER.debug("Pool: discarded bad connection, created=%d", self._created)
    
    def get_status(self) -> dict:
        """Get current pool status for monitoring."""
        with self._lock:
            return {
                "created": self._created,
                "available": len(self._pool),
                "max": self._max_connections,
                "in_use": self._created - len(self._pool),
            }
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection with optimized settings."""
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        
        # Enable WAL mode for better concurrent read performance
        conn.execute("PRAGMA journal_mode=WAL;")
        
        # Enable foreign key constraints
        conn.execute("PRAGMA foreign_keys=ON;")
        
        # Optimize for performance
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA cache_size=-64000;")  # 64MB cache
        conn.execute("PRAGMA temp_store=MEMORY;")
        
        return conn
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                try:
                    conn.close()
                except Exception:
                    pass
            self._pool.clear()
            self._created = 0


class PooledConnection:
    """
    Context manager for pooled connections.
    Automatically returns the connection to the pool when done.
    """
    
    def __init__(self, pool: SQLiteConnectionPool):
        self._pool = pool
        self._conn = None
        self._acquired_time = None
        self._acquired_thread = None
        
    def __enter__(self) -> sqlite3.Connection:
        import time
        self._conn = self._pool.get_connection()
        self._acquired_time = time.time()
        self._acquired_thread = threading.current_thread().name
        return self._conn
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        if self._conn:
            # Check for connection leak (held > 60 seconds)
            if self._acquired_time:
                held_duration = time.time() - self._acquired_time
                if held_duration > 60.0:
                    LOGGER.warning(
                        "Connection leak detected: held for %.1fs by thread %s",
                        held_duration,
                        self._acquired_thread,
                    )
            
            self._pool.return_connection(self._conn)
            self._conn = None
