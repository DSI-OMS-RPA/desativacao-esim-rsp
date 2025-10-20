# helpers/lock_manager.py
"""
Process Lock Manager for eSIM Deactivation Process

Prevents concurrent executions using PID-based locking mechanism.
"""

import os
import sys
import signal
import atexit
import logging
from pathlib import Path
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ProcessLock:
    """
    Manages process locking to prevent concurrent executions.

    Uses a PID file to track running processes and verify if they're still active.
    Automatically releases lock on process exit.
    """

    def __init__(self, lock_dir: str = "/tmp", lock_name: str = "esim_deactivation"):
        """
        Initialize the process lock.

        Args:
            lock_dir: Directory where lock file will be created
            lock_name: Name of the lock file (without extension)
        """
        self.lock_file = Path(lock_dir) / f"{lock_name}.lock"
        self.pid = os.getpid()
        self.locked = False

        # Register cleanup handlers
        atexit.register(self.release)
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        logger.debug(f"ProcessLock initialized with file: {self.lock_file}")

    def _signal_handler(self, signum, frame):
        """Handle termination signals gracefully."""
        logger.info(f"Received signal {signum}, releasing lock...")
        self.release()
        sys.exit(0)

    def acquire(self, force: bool = False) -> bool:
        """
        Acquire the process lock.

        Args:
            force: If True, forcefully acquire lock even if another process holds it

        Returns:
            True if lock was acquired, False otherwise

        Raises:
            RuntimeError: If another process is already running (when force=False)
        """
        if self.locked:
            logger.debug("Lock already held by this process")
            return True

        if self.is_locked() and not force:
            other_pid = self._read_pid()
            error_msg = f"Another process (PID: {other_pid}) is already running"
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        try:
            # Create lock directory if it doesn't exist
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)

            # Write PID to lock file
            self.lock_file.write_text(f"{self.pid}\n{datetime.now().isoformat()}")
            self.locked = True

            logger.info(f"Lock acquired successfully (PID: {self.pid})")
            return True

        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    def release(self) -> bool:
        """
        Release the process lock.

        Returns:
            True if lock was released, False if it wasn't held
        """
        if not self.locked:
            return False

        try:
            if self.lock_file.exists():
                # Verify we own the lock before removing
                if self._read_pid() == self.pid:
                    self.lock_file.unlink()
                    logger.info(f"Lock released (PID: {self.pid})")
                else:
                    logger.warning("Lock file exists but owned by different process")

            self.locked = False
            return True

        except Exception as e:
            logger.error(f"Error releasing lock: {e}")
            return False

    def is_locked(self) -> bool:
        """
        Check if a lock is currently held by any process.

        Returns:
            True if a valid lock exists, False otherwise
        """
        if not self.lock_file.exists():
            return False

        try:
            pid = self._read_pid()
            if pid is None:
                return False

            # Check if process is still running
            if self._is_process_running(pid):
                return True
            else:
                # Stale lock file - remove it
                logger.warning(f"Removing stale lock file (PID {pid} not running)")
                self.lock_file.unlink()
                return False

        except Exception as e:
            logger.error(f"Error checking lock status: {e}")
            return False

    def _read_pid(self) -> Optional[int]:
        """Read PID from lock file."""
        try:
            content = self.lock_file.read_text().strip()
            # PID is on first line
            pid_str = content.split('\n')[0]
            return int(pid_str)
        except Exception:
            return None

    def _is_process_running(self, pid: int) -> bool:
        """
        Check if a process with given PID is running.

        Cross-platform implementation using os.kill with signal 0.
        """
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
        except Exception:
            return False

    def get_lock_info(self) -> Optional[dict]:
        """
        Get information about current lock.

        Returns:
            Dictionary with lock info or None if no lock exists
        """
        if not self.lock_file.exists():
            return None

        try:
            content = self.lock_file.read_text().strip().split('\n')
            pid = int(content[0])
            timestamp = content[1] if len(content) > 1 else "Unknown"

            return {
                "pid": pid,
                "timestamp": timestamp,
                "is_running": self._is_process_running(pid),
                "lock_file": str(self.lock_file)
            }
        except Exception as e:
            logger.error(f"Error reading lock info: {e}")
            return None

    def __enter__(self):
        """Context manager entry."""
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()

    def __del__(self):
        """Cleanup on object destruction."""
        self.release()


# Utility functions for CLI usage
def check_lock_status(lock_dir: str = "/tmp", lock_name: str = "esim_deactivation") -> None:
    """
    Check and print current lock status.

    Useful for debugging and monitoring.
    """
    lock = ProcessLock(lock_dir, lock_name)
    info = lock.get_lock_info()

    if info:
        print(f"Lock Status: ACTIVE")
        print(f"  PID: {info['pid']}")
        print(f"  Started: {info['timestamp']}")
        print(f"  Process Running: {info['is_running']}")
        print(f"  Lock File: {info['lock_file']}")
    else:
        print("Lock Status: NOT ACTIVE")


def force_unlock(lock_dir: str = "/tmp", lock_name: str = "esim_deactivation") -> None:
    """
    Forcefully remove lock file.

    Use with caution - only when certain no process is running.
    """
    lock_file = Path(lock_dir) / f"{lock_name}.lock"
    if lock_file.exists():
        lock_file.unlink()
        print(f"Lock file removed: {lock_file}")
    else:
        print("No lock file found")


if __name__ == "__main__":
    # CLI interface for lock management
    import argparse

    parser = argparse.ArgumentParser(description="Process Lock Manager")
    parser.add_argument("action", choices=["status", "force-unlock"],
                       help="Action to perform")
    parser.add_argument("--lock-dir", default="/tmp",
                       help="Lock directory")
    parser.add_argument("--lock-name", default="esim_deactivation",
                       help="Lock name")

    args = parser.parse_args()

    if args.action == "status":
        check_lock_status(args.lock_dir, args.lock_name)
    elif args.action == "force-unlock":
        force_unlock(args.lock_dir, args.lock_name)
