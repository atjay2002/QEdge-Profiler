"""
QEdge Profiler Database Layer
SQLite database with thread-safe operations for sessions, snapshots, and analysis results.
"""

import sqlite3
import json
import threading
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import os

# Thread-safe database access
db_lock = threading.Lock()

# Database file path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'qedge_profiler.db')


def get_connection() -> sqlite3.Connection:
    """Get a database connection with Row factory for dict-like access."""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database schema - create all tables if they don't exist."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        # Table 1: sessions - Master table for each benchmark/monitoring run
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_type TEXT NOT NULL CHECK(session_type IN ('benchmark', 'watch', 'combined')),
                model_name TEXT,
                backend TEXT CHECK(backend IN ('CPU', 'GPU', 'NPU') OR backend IS NULL),
                precision TEXT CHECK(precision IN ('FP32', 'FP16', 'INT8') OR precision IS NULL),
                pid INTEGER,
                start_time INTEGER NOT NULL,
                end_time INTEGER,
                status TEXT NOT NULL CHECK(status IN ('running', 'completed', 'failed')) DEFAULT 'running',
                metadata TEXT
            )
        ''')

        # Table 2: snapshots - Time-series memory/CPU data
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                rss_mb REAL NOT NULL,
                vms_mb REAL,
                cpu_percent REAL,
                thread_count INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_snapshots_session_timestamp
            ON snapshots(session_id, timestamp)
        ''')

        # Table 3: benchmark_results - Performance metrics
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE,
                latency_p50_ms REAL,
                latency_p95_ms REAL,
                latency_p99_ms REAL,
                fps REAL,
                iterations INTEGER,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')

        # Table 4: leak_analysis - Leak detection results
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leak_analysis (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE,
                leak_score REAL NOT NULL,
                regression_slope REAL,
                r_squared REAL,
                growth_rate_mb_per_min REAL,
                peak_rss_mb REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')

        # Table 5: health_scores - Composite metric
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS health_scores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL UNIQUE,
                health_score REAL NOT NULL,
                fps_component REAL,
                leak_component REAL,
                memory_component REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')

        # Table 6: alerts - Leak alert history
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp INTEGER NOT NULL,
                severity TEXT NOT NULL CHECK(severity IN ('warning', 'critical')),
                message TEXT NOT NULL,
                acknowledged INTEGER DEFAULT 0,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')

        # Table 7: tracemalloc_snapshots - Python memory allocations
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracemalloc_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                line_no INTEGER,
                file_path TEXT,
                size_mb REAL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            )
        ''')

        conn.commit()
        conn.close()


# ============================================================================
# Session Management
# ============================================================================

def create_session(
    session_type: str,
    pid: Optional[int] = None,
    model_name: Optional[str] = None,
    backend: Optional[str] = None,
    precision: Optional[str] = None,
    metadata: Optional[Dict] = None
) -> int:
    """Create a new session and return its ID."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        start_time = int(datetime.now().timestamp())
        metadata_json = json.dumps(metadata) if metadata else None

        cursor.execute('''
            INSERT INTO sessions
            (session_type, model_name, backend, precision, pid, start_time, status, metadata)
            VALUES (?, ?, ?, ?, ?, ?, 'running', ?)
        ''', (session_type, model_name, backend, precision, pid, start_time, metadata_json))

        session_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return session_id


def update_session_status(session_id: int, status: str, end_time: Optional[int] = None):
    """Update session status and optionally set end time."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        if end_time is None and status in ('completed', 'failed'):
            end_time = int(datetime.now().timestamp())

        cursor.execute('''
            UPDATE sessions
            SET status = ?, end_time = ?
            WHERE id = ?
        ''', (status, end_time, session_id))

        conn.commit()
        conn.close()


def get_session(session_id: int) -> Optional[Dict]:
    """Get session details by ID."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM sessions WHERE id = ?', (session_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return dict(row)
        return None


def get_session_history(
    limit: int = 50,
    session_type: Optional[str] = None,
    model_name: Optional[str] = None,
    backend: Optional[str] = None
) -> List[Dict]:
    """Get session history with optional filters."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        query = 'SELECT * FROM sessions WHERE 1=1'
        params = []

        if session_type:
            query += ' AND session_type = ?'
            params.append(session_type)
        if model_name:
            query += ' AND model_name = ?'
            params.append(model_name)
        if backend:
            query += ' AND backend = ?'
            params.append(backend)

        query += ' ORDER BY start_time DESC LIMIT ?'
        params.append(limit)

        cursor.execute(query, params)
        rows = cursor.fetchall()

        conn.close()

        return [dict(row) for row in rows]


# ============================================================================
# Snapshot Management
# ============================================================================

def insert_snapshot(
    session_id: int,
    rss_mb: float,
    vms_mb: Optional[float] = None,
    cpu_percent: Optional[float] = None,
    thread_count: Optional[int] = None,
    timestamp: Optional[int] = None
):
    """Insert a memory/CPU snapshot."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        if timestamp is None:
            timestamp = int(datetime.now().timestamp() * 1000)  # milliseconds

        cursor.execute('''
            INSERT INTO snapshots
            (session_id, timestamp, rss_mb, vms_mb, cpu_percent, thread_count)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, timestamp, rss_mb, vms_mb, cpu_percent, thread_count))

        conn.commit()
        conn.close()


def get_snapshots(session_id: int) -> List[Dict]:
    """Get all snapshots for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM snapshots
            WHERE session_id = ?
            ORDER BY timestamp ASC
        ''', (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


# ============================================================================
# Benchmark Results
# ============================================================================

def insert_benchmark_results(
    session_id: int,
    latency_p50_ms: float,
    latency_p95_ms: float,
    latency_p99_ms: float,
    fps: float,
    iterations: int
):
    """Insert benchmark performance results."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO benchmark_results
            (session_id, latency_p50_ms, latency_p95_ms, latency_p99_ms, fps, iterations)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, latency_p50_ms, latency_p95_ms, latency_p99_ms, fps, iterations))

        conn.commit()
        conn.close()


def get_benchmark_results(session_id: int) -> Optional[Dict]:
    """Get benchmark results for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM benchmark_results WHERE session_id = ?', (session_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return dict(row)
        return None


# ============================================================================
# Leak Analysis
# ============================================================================

def insert_leak_analysis(
    session_id: int,
    leak_score: float,
    regression_slope: float,
    r_squared: float,
    growth_rate_mb_per_min: float,
    peak_rss_mb: float
):
    """Insert leak analysis results."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO leak_analysis
            (session_id, leak_score, regression_slope, r_squared, growth_rate_mb_per_min, peak_rss_mb)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (session_id, leak_score, regression_slope, r_squared, growth_rate_mb_per_min, peak_rss_mb))

        conn.commit()
        conn.close()


def get_leak_analysis(session_id: int) -> Optional[Dict]:
    """Get leak analysis for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM leak_analysis WHERE session_id = ?', (session_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return dict(row)
        return None


# ============================================================================
# Health Scores
# ============================================================================

def insert_health_score(
    session_id: int,
    health_score: float,
    fps_component: float,
    leak_component: float,
    memory_component: float
):
    """Insert health score results."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT OR REPLACE INTO health_scores
            (session_id, health_score, fps_component, leak_component, memory_component)
            VALUES (?, ?, ?, ?, ?)
        ''', (session_id, health_score, fps_component, leak_component, memory_component))

        conn.commit()
        conn.close()


def get_health_score(session_id: int) -> Optional[Dict]:
    """Get health score for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM health_scores WHERE session_id = ?', (session_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return dict(row)
        return None


# ============================================================================
# Alerts
# ============================================================================

def insert_alert(session_id: int, severity: str, message: str):
    """Insert a new alert."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        timestamp = int(datetime.now().timestamp())

        cursor.execute('''
            INSERT INTO alerts (session_id, timestamp, severity, message)
            VALUES (?, ?, ?, ?)
        ''', (session_id, timestamp, severity, message))

        conn.commit()
        conn.close()


def get_alerts(session_id: int) -> List[Dict]:
    """Get all alerts for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM alerts
            WHERE session_id = ?
            ORDER BY timestamp DESC
        ''', (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


# ============================================================================
# Tracemalloc Snapshots
# ============================================================================

def insert_tracemalloc_snapshot(session_id: int, line_no: int, file_path: str, size_mb: float):
    """Insert a tracemalloc allocation snapshot."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO tracemalloc_snapshots (session_id, line_no, file_path, size_mb)
            VALUES (?, ?, ?, ?)
        ''', (session_id, line_no, file_path, size_mb))

        conn.commit()
        conn.close()


def get_tracemalloc_snapshots(session_id: int) -> List[Dict]:
    """Get top memory allocations for a session."""
    with db_lock:
        conn = get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM tracemalloc_snapshots
            WHERE session_id = ?
            ORDER BY size_mb DESC
        ''', (session_id,))

        rows = cursor.fetchall()
        conn.close()

        return [dict(row) for row in rows]


# ============================================================================
# Session Comparison
# ============================================================================

def compare_sessions(session_id1: int, session_id2: int) -> Dict[str, Any]:
    """Compare two sessions side by side."""
    with db_lock:
        conn = get_connection()

        # Get both sessions
        session1 = get_session(session_id1)
        session2 = get_session(session_id2)

        # Get snapshots
        snapshots1 = get_snapshots(session_id1)
        snapshots2 = get_snapshots(session_id2)

        # Get leak analysis
        leak1 = get_leak_analysis(session_id1)
        leak2 = get_leak_analysis(session_id2)

        # Get benchmark results
        bench1 = get_benchmark_results(session_id1)
        bench2 = get_benchmark_results(session_id2)

        # Get health scores
        health1 = get_health_score(session_id1)
        health2 = get_health_score(session_id2)

        conn.close()

        return {
            'session1': {
                'session': session1,
                'snapshots': snapshots1,
                'leak_analysis': leak1,
                'benchmark_results': bench1,
                'health_score': health1
            },
            'session2': {
                'session': session2,
                'snapshots': snapshots2,
                'leak_analysis': leak2,
                'benchmark_results': bench2,
                'health_score': health2
            }
        }


# Initialize database on module import
init_database()
