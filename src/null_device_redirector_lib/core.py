"""Redirect stdout and stderr to os.devnull for the duration of a block.

Why this exists
---------------
Some C-level extensions and third-party libraries write directly to the
process-wide ``sys.stdout`` / ``sys.stderr`` file descriptors (fd 1 and
fd 2). The usual ``contextlib.redirect_stdout`` only swaps the Python
object bound to ``sys.stdout``; it does not touch the underlying file
descriptor, so output from those libraries still leaks to the terminal.

This module provides a context manager that redirects at the file
descriptor level using ``os.dup2``. That is the only reliable way to
silence code that writes to fd 1 or fd 2 without going through Python's
``sys`` module.

Trade-off
---------
File-descriptor redirection is process-global. While the context manager
is active, *all* writes to fd 1 and fd 2 from any thread in the process
are discarded, not just writes from the block that entered the context.
Python's object-level redirection is thread-local-ish and can be nested
safely; this one cannot be nested in a meaningful way. We choose the
process-global behaviour because it is the only way to catch C-level
writers, and we document the limitation rather than pretend it does not
exist.

Awkward edge
------------
If the process has closed fd 1 or fd 2 before entering the context, the
``os.dup`` call that saves the original descriptor will raise
``OSError``. Rather than silently doing nothing, we let that error
propagate: a caller who has already closed the standard streams has a
bug that should be visible.
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

__all__ = ["redirect_to_devnull"]


@contextmanager
def redirect_to_devnull() -> Iterator[None]:
    """Redirect file descriptors 1 and 2 to ``os.devnull`` for the block.

    On entry, the current fd 1 and fd 2 are duplicated so they can be
    restored on exit. New descriptors are opened on ``os.devnull`` and
    installed with ``os.dup2``. On exit, the saved descriptors are
    restored and the temporary devnull descriptors are closed.

    The context manager is not re-entrant and not thread-safe; see the
    module docstring for why that is an intentional trade-off.
    """
    # Save the original descriptors *before* opening the devnull sink.
    # If either standard descriptor is already closed this raises OSError,
    # which we deliberately do not swallow: a closed standard stream is a
    # real bug in the caller. Saving first also means a failure here does
    # not leak the devnull descriptor.
    saved_stdout_fd = os.dup(1)
    saved_stderr_fd = os.dup(2)

    # ``os.devnull`` is the platform's null device (``/dev/null`` on
    # POSIX, ``NUL`` on Windows). Opening it in append mode is the
    # conventional way to get a writable sink that discards data.
    devnull_fd = os.open(os.devnull, os.O_WRONLY)

    try:
        os.dup2(devnull_fd, 1)
        os.dup2(devnull_fd, 2)
        yield
    finally:
        # Restore first, then close the saved descriptors. If we closed
        # them before restoring, a failure in ``os.dup2`` would leave the
        # process with no usable standard streams at all.
        os.dup2(saved_stdout_fd, 1)
        os.dup2(saved_stderr_fd, 2)
        os.close(saved_stdout_fd)
        os.close(saved_stderr_fd)
        os.close(devnull_fd)
