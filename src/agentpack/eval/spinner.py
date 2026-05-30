"""Lightweight terminal spinner + step logger for the eval pipelines.

The spinner animates braille dots on a background thread so long, otherwise
silent steps (Docling pack build, embedding-model download) show liveness and
don't look hung. When stderr is not a TTY (e.g. output redirected to a file)
it degrades to plain start/done lines instead of control characters.
"""
import sys
import time
import itertools
import threading
from contextlib import contextmanager

_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


@contextmanager
def spinner(message: str, stream=None):
    """Context manager that animates `message` until the block exits."""
    stream = stream or sys.stderr
    is_tty = hasattr(stream, "isatty") and stream.isatty()
    start = time.time()

    if not is_tty:
        stream.write(f"… {message}\n")
        stream.flush()
        try:
            yield
        finally:
            stream.write(f"✓ {message} ({time.time() - start:.1f}s)\n")
            stream.flush()
        return

    stop = threading.Event()

    def _spin():
        for frame in itertools.cycle(_FRAMES):
            if stop.is_set():
                break
            elapsed = time.time() - start
            stream.write(f"\r{frame} {message} … {elapsed:5.1f}s")
            stream.flush()
            time.sleep(0.1)

    thread = threading.Thread(target=_spin, daemon=True)
    thread.start()
    ok = True
    try:
        yield
    except BaseException:
        ok = False
        raise
    finally:
        stop.set()
        thread.join()
        mark = "✓" if ok else "✗"
        stream.write(f"\r{mark} {message} … done in {time.time() - start:.1f}s" + " " * 8 + "\n")
        stream.flush()


class StepLogger:
    """Tracks numbered phases and emits verbose detail lines.

    `phase()` announces the current high-level step and how many remain;
    `detail()` prints fine-grained lines only when `verbose` is on.
    """

    def __init__(self, total_phases: int, verbose: bool = False, stream=None):
        self.total = total_phases
        self.verbose = verbose
        self.current = 0
        self.stream = stream or sys.stderr

    def phase(self, title: str):
        self.current += 1
        remaining = self.total - self.current
        bar = f"[Phase {self.current}/{self.total}]"
        suffix = f"  ({remaining} phase{'s' if remaining != 1 else ''} remaining)" if remaining else "  (final phase)"
        self.stream.write(f"\n\033[1m{bar}\033[0m {title}{suffix}\n")
        self.stream.flush()

    def detail(self, msg: str):
        if self.verbose:
            self.stream.write(f"    · {msg}\n")
            self.stream.flush()
