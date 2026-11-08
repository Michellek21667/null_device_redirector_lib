# null_device_redirector_lib

Redirect stdout and stderr to `os.devnull` for the duration of a block, then restore them.

```python
import os
from null_device_redirector_lib import redirect_to_devnull

with redirect_to_devnull():
    os.write(1, b"this goes to /dev/null\n")
    os.write(2, b"so does this\n")

os.write(1, b"this reaches the real stdout\n")
```

## Why this exists

`contextlib.redirect_stdout` and `contextlib.redirect_stderr` replace the
Python objects bound to `sys.stdout` and `sys.stderr`. They do not touch the
underlying file descriptors (1 and 2), so any code that writes through those
descriptors — C extensions, subprocesses that inherit the descriptors,
libraries that call `os.write` directly — keeps printing to the terminal.

This library redirects at the file-descriptor level with `os.dup2`, which is
the only way to silence those writers. The trade-off is that the redirection
is process-global: while the context manager is active, every thread in the
process loses its standard output and error. There is no way to make
file-descriptor redirection thread-local, so the library does not pretend to.

## The awkward edge

If fd 1 or fd 2 is already closed when the context manager is entered, the
`os.dup` call used to save the original descriptor raises `OSError`. That
error propagates rather than being swallowed: a caller with closed standard
streams has a bug that should be visible. The same applies if the descriptors
are closed while the block runs — the restore in the `finally` clause will
raise, and the original exception (if any) will be chained.

## API

`redirect_to_devnull()` — a context manager. Exported from the package root.
