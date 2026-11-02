"""Slow work off the UI thread: a queued job worker, a coalesced refresh, and a newest-value-only handoff."""
import itertools
import threading
import time

from PySide6.QtCore import QObject, QThread, Signal, Slot


class Worker(QObject):
    """Runs jobs on its own thread, one at a time, in the order they were submitted.

    The UI takes a job id with reserve(), shows a pending row for it, then calls submit(); it fills the row in
    when `finished` or `failed` arrives with that id. Reserving first means even a job that ends at once
    (a direct connection, a cache hit) finds its row. Everything that touches one slow resource (a device,
    a socket, a database file) goes through one worker, so calls never interleave."""

    request = Signal(int, object)      # (job id, callable)
    finished = Signal(int, object)     # (job id, result)
    failed = Signal(int, str)          # (job id, error text)
    timed = Signal(int, float)         # (job id, seconds the call took): measure, never guess, latency
    poll = Signal()
    refreshed = Signal(object)

    def __init__(self, refresh=None):
        super().__init__()
        self._ids = itertools.count(1)
        self._refresh, self._poll_queued = refresh, False
        self.request.connect(self._run)
        self.poll.connect(self._polled)

    def reserve(self):
        return next(self._ids)

    def submit(self, call, job=None):
        """Queues `call()` on the worker thread; returns its job id (safe to call from the UI thread)."""
        job = self.reserve() if job is None else job
        self.request.emit(job, call)
        return job

    @Slot(int, object)
    def _run(self, job, call):
        start = time.perf_counter()
        try:
            result = call()
        except Exception as err:       # a job failure is shown to the user, never raised into Qt
            self.failed.emit(job, str(err) or type(err).__name__)
        else:
            self.finished.emit(job, result)
        finally:
            self.timed.emit(job, time.perf_counter() - start)

    def request_poll(self):
        """Queues one refresh unless one is already waiting: refreshes queued faster than they run would hold
        every user action back behind them."""
        if self._refresh and not self._poll_queued:
            self._poll_queued = True
            self.poll.emit()

    @Slot()
    def _polled(self):
        self._poll_queued = False
        try:
            self.refreshed.emit(self._refresh())
        except Exception as err:
            self.failed.emit(0, f"Refresh failed: {err}")


def start(worker):
    """Moves `worker` to a new running thread; call stop() with the result before the app quits."""
    thread = QThread()
    worker.moveToThread(thread)
    thread.start()
    return thread


def stop(thread, wait_ms=5000):
    thread.quit()
    thread.wait(wait_ms)


class Latest:
    """Producer-to-UI handoff that keeps only the newest value, so a slow UI shows the latest, not a backlog.

    The producer thread calls put(); it returns True only for the first value since the last take(), which is
    when the producer should emit its "ready" signal. The UI slot calls take()."""

    def __init__(self):
        self._lock = threading.Lock()
        self._value, self._signalled, self.at = None, False, 0.0

    def put(self, value):
        with self._lock:
            self._value, self.at = value, time.monotonic()
            first, self._signalled = not self._signalled, True
            return first

    def take(self):
        with self._lock:
            value, self._value, self._signalled = self._value, None, False
            return value
