"""
QEdge Profiler Memory Watcher
Background daemon thread that monitors process memory and CPU usage via psutil.
"""

import psutil
import threading
import time
import queue
from typing import Optional, Dict
from datetime import datetime

from database import db


class MemoryWatcher:
    """Monitors a process's memory and CPU usage in real-time."""

    def __init__(
        self,
        pid: int,
        session_id: int,
        snapshot_queue: Optional[queue.Queue] = None,
        poll_interval: float = 0.5
    ):
        """
        Initialize memory watcher.

        Args:
            pid: Process ID to monitor
            session_id: Database session ID
            snapshot_queue: Optional queue for real-time updates (SSE)
            poll_interval: Polling interval in seconds (default 0.5s)
        """
        self.pid = pid
        self.session_id = session_id
        self.snapshot_queue = snapshot_queue
        self.poll_interval = poll_interval

        self._stop_event = threading.Event()
        self._monitor_thread: Optional[threading.Thread] = None
        self._process: Optional[psutil.Process] = None

        # Statistics
        self.snapshot_count = 0
        self.is_running = False

    def start_monitoring(self):
        """Start the monitoring daemon thread."""
        if self._monitor_thread and self._monitor_thread.is_alive():
            print(f"[MemoryWatcher] Already monitoring PID {self.pid}")
            return

        # Verify PID exists before starting
        if not psutil.pid_exists(self.pid):
            raise ProcessLookupError(f"Process with PID {self.pid} does not exist")

        try:
            self._process = psutil.Process(self.pid)
            if not self._process.is_running():
                raise ProcessLookupError(f"Process {self.pid} is not running")
        except psutil.NoSuchProcess:
            raise ProcessLookupError(f"Process {self.pid} does not exist")

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name=f"MemoryWatcher-{self.pid}"
        )
        self._monitor_thread.start()
        self.is_running = True

        print(f"[MemoryWatcher] Started monitoring PID {self.pid} (session {self.session_id})")

    def stop_monitoring(self):
        """Stop the monitoring thread."""
        if not self._monitor_thread:
            return

        print(f"[MemoryWatcher] Stopping monitor for PID {self.pid}")
        self._stop_event.set()

        # Wait for thread to finish (with timeout)
        self._monitor_thread.join(timeout=5.0)
        self.is_running = False

        print(f"[MemoryWatcher] Stopped monitoring PID {self.pid}. Total snapshots: {self.snapshot_count}")

    def _monitor_loop(self):
        """Internal monitoring loop (runs in daemon thread)."""
        try:
            while not self._stop_event.is_set():
                # Check if process still exists
                if not psutil.pid_exists(self.pid):
                    print(f"[MemoryWatcher] PID {self.pid} no longer exists. Stopping.")
                    break

                try:
                    # Verify process is still accessible
                    if not self._process.is_running():
                        print(f"[MemoryWatcher] Process {self.pid} is no longer running. Stopping.")
                        break

                    # Collect metrics
                    snapshot = self._collect_snapshot()

                    if snapshot:
                        # Store to database
                        db.insert_snapshot(
                            session_id=self.session_id,
                            rss_mb=snapshot['rss_mb'],
                            vms_mb=snapshot['vms_mb'],
                            cpu_percent=snapshot['cpu_percent'],
                            thread_count=snapshot['thread_count'],
                            timestamp=snapshot['timestamp']
                        )

                        # Send to queue for real-time SSE (if configured)
                        if self.snapshot_queue:
                            try:
                                self.snapshot_queue.put_nowait(snapshot)
                            except queue.Full:
                                pass  # Skip if queue full

                        self.snapshot_count += 1

                except psutil.NoSuchProcess:
                    print(f"[MemoryWatcher] Process {self.pid} disappeared. Stopping.")
                    break
                except psutil.AccessDenied:
                    print(f"[MemoryWatcher] Access denied to process {self.pid}. Stopping.")
                    break
                except Exception as e:
                    print(f"[MemoryWatcher] Error collecting snapshot: {e}")

                # Sleep until next poll
                time.sleep(self.poll_interval)

        except Exception as e:
            print(f"[MemoryWatcher] Fatal error in monitor loop: {e}")
        finally:
            self.is_running = False
            # Update session status if process terminated
            db.update_session_status(self.session_id, 'completed')

    def _collect_snapshot(self) -> Optional[Dict]:
        """
        Collect current process metrics.

        Returns:
            Dictionary with rss_mb, vms_mb, cpu_percent, thread_count, timestamp
        """
        try:
            # Memory info
            mem_info = self._process.memory_info()
            rss_mb = mem_info.rss / (1024 * 1024)  # Convert bytes to MB
            vms_mb = mem_info.vms / (1024 * 1024) if hasattr(mem_info, 'vms') else 0.0

            # CPU percent (non-blocking)
            cpu_percent = self._process.cpu_percent(interval=None)

            # Thread count
            try:
                thread_count = self._process.num_threads()
            except (psutil.AccessDenied, AttributeError):
                thread_count = 0

            # Timestamp (milliseconds since epoch)
            timestamp = int(datetime.now().timestamp() * 1000)

            return {
                'session_id': self.session_id,
                'pid': self.pid,
                'rss_mb': round(rss_mb, 2),
                'vms_mb': round(vms_mb, 2),
                'cpu_percent': round(cpu_percent, 2),
                'thread_count': thread_count,
                'timestamp': timestamp
            }

        except Exception as e:
            print(f"[MemoryWatcher] Error collecting metrics: {e}")
            return None

    def get_current_stats(self) -> Optional[Dict]:
        """Get current process stats (non-blocking)."""
        if not psutil.pid_exists(self.pid):
            return None

        try:
            return self._collect_snapshot()
        except:
            return None


def attach_to_process(pid: int, session_id: Optional[int] = None, snapshot_queue: Optional[queue.Queue] = None) -> MemoryWatcher:
    """
    Attach memory watcher to an existing process.

    Args:
        pid: Process ID
        session_id: Optional existing session ID, creates new if None
        snapshot_queue: Optional queue for real-time updates

    Returns:
        MemoryWatcher instance (already started)
    """
    # Create session if not provided
    if session_id is None:
        session_id = db.create_session(
            session_type='watch',
            pid=pid
        )

    # Create and start watcher
    watcher = MemoryWatcher(
        pid=pid,
        session_id=session_id,
        snapshot_queue=snapshot_queue
    )

    watcher.start_monitoring()

    return watcher


def get_process_info(pid: int) -> Optional[Dict]:
    """
    Get process information without starting monitoring.

    Args:
        pid: Process ID

    Returns:
        Dictionary with process name, cmdline, status, memory info or None if not found
    """
    if not psutil.pid_exists(pid):
        return None

    try:
        proc = psutil.Process(pid)

        mem_info = proc.memory_info()

        return {
            'pid': pid,
            'name': proc.name(),
            'cmdline': ' '.join(proc.cmdline()),
            'status': proc.status(),
            'rss_mb': round(mem_info.rss / (1024 * 1024), 2),
            'vms_mb': round(mem_info.vms / (1024 * 1024), 2) if hasattr(mem_info, 'vms') else 0.0,
            'cpu_percent': proc.cpu_percent(interval=0.1),
            'num_threads': proc.num_threads()
        }

    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None


def find_processes_by_name(name: str) -> list[Dict]:
    """
    Find running processes by name.

    Args:
        name: Process name to search for (partial match)

    Returns:
        List of process info dictionaries
    """
    matches = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if name.lower() in proc.info['name'].lower():
                info = get_process_info(proc.info['pid'])
                if info:
                    matches.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    return matches
