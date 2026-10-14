"""Background jobs (archiving, verification, restore, extraction, similar images):
one thread per job, progress read by the interface with /api/job."""
from __future__ import annotations

import threading
import time

from .utils import Cancelled, describe_os_error


class Job:
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.state = "running"          # running | done | cancelled | error
        self.phase = ""
        self.done = 0
        self.total = 0
        self.bytes_done = 0
        self.bytes_total = 0
        self.current = ""
        self.message = ""
        self.result = None
        self.cancel = threading.Event()
        self.started = time.time()
        self.finished = 0.0

    def check(self) -> None:
        if self.cancel.is_set():
            raise Cancelled()

    def status(self) -> dict:
        end = self.finished or time.time()
        return {"kind": self.kind, "state": self.state, "phase": self.phase, "done": self.done,
                "total": self.total, "bytes_done": self.bytes_done, "bytes_total": self.bytes_total,
                "current": self.current, "message": self.message, "result": self.result,
                "elapsed": round(end - self.started, 1)}


_lock = threading.Lock()
JOBS: dict[str, Job] = {}


def start(kind: str, fn, *args) -> Job:
    """Runs fn(job, *args) in a thread; its return value becomes job.result.
    Only one job of each kind at a time."""
    with _lock:
        old = JOBS.get(kind)
        if old and old.state == "running":
            raise ValueError("This operation is already running.")
        job = JOBS[kind] = Job(kind)

    def run() -> None:
        try:
            job.result = fn(job, *args)
            job.state = "done"
        except Cancelled:
            job.state = "cancelled"
        except ValueError as e:                 # a clear message for the user
            job.state, job.message = "error", str(e)
        except OSError as e:
            job.state, job.message = "error", describe_os_error(e)
        except Exception as e:  # noqa: BLE001
            job.state, job.message = "error", f"{type(e).__name__}: {e}"
        finally:
            job.finished = time.time()
            job.current = ""

    threading.Thread(target=run, daemon=True).start()
    return job


def status(kind: str) -> dict:
    job = JOBS.get(kind)
    return job.status() if job else {"kind": kind, "state": "idle"}


def cancel(kind: str) -> None:
    job = JOBS.get(kind)
    if job:
        job.cancel.set()
