"""Tests for null_device_redirector_lib.

These tests exercise the file-descriptor redirection directly by writing
to fd 1 and fd 2 with ``os.write``. That bypasses Python's ``sys.stdout``
object and is exactly the path the library is designed to intercept, so
the tests validate the real behaviour rather than a Python-level
approximation of it.
"""

import os
import unittest

from null_device_redirector_lib import redirect_to_devnull


class RedirectToDevnullTests(unittest.TestCase):
    def _read_fd(self, fd: int) -> bytes:
        """Read whatever is currently buffered on ``fd`` without blocking.

        We use a pipe with a non-blocking read so we can observe writes
        made by the context manager without hanging when nothing was
        written. The caller is responsible for setting the fd to
        non-blocking before calling this.
        """
        try:
            return os.read(fd, 4096)
        except BlockingIOError:
            return b""

    def test_writes_inside_block_are_discarded(self) -> None:
        # Create a pipe and point fd 1 at the write end so we can observe
        # what actually reaches the standard output descriptor.
        read_fd, write_fd = os.pipe()
        os.set_blocking(read_fd, False)
        saved_stdout = os.dup(1)
        try:
            os.dup2(write_fd, 1)
            with redirect_to_devnull():
                os.write(1, b"this should disappear\n")
                os.write(2, b"so should this\n")
            # After the context exits, fd 1 is restored to the pipe write
            # end, so a direct write is observable again.
            os.write(1, b"visible\n")
            os.close(write_fd)
            write_fd = -1  # mark as closed so finally does not double-close
            data = self._read_fd(read_fd)
        finally:
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)
            if write_fd != -1:
                os.close(write_fd)
            os.close(read_fd)

        self.assertEqual(data, b"visible\n")

    def test_stdout_and_stderr_are_restored(self) -> None:
        # Capture the original descriptors so we can compare after the
        # context manager has run. We compare the *targets*, not the
        # descriptor numbers, because dup2 may reuse numbers.
        original_stdout = os.dup(1)
        original_stderr = os.dup(2)
        try:
            with redirect_to_devnull():
                # Inside the block, fd 1 and fd 2 should point at the
                # same devnull file, which is not the original target.
                self.assertNotEqual(os.fstat(1).st_ino, os.fstat(original_stdout).st_ino)
                self.assertNotEqual(os.fstat(2).st_ino, os.fstat(original_stderr).st_ino)
            # After the block, fd 1 and fd 2 should be back to the
            # original file descriptions.
            self.assertEqual(os.fstat(1).st_ino, os.fstat(original_stdout).st_ino)
            self.assertEqual(os.fstat(2).st_ino, os.fstat(original_stderr).st_ino)
        finally:
            os.close(original_stdout)
            os.close(original_stderr)

    def test_exception_inside_block_restores_streams(self) -> None:
        original_stdout = os.dup(1)
        original_stderr = os.dup(2)
        try:
            with self.assertRaises(RuntimeError):
                with redirect_to_devnull():
                    raise RuntimeError("boom")
            self.assertEqual(os.fstat(1).st_ino, os.fstat(original_stdout).st_ino)
            self.assertEqual(os.fstat(2).st_ino, os.fstat(original_stderr).st_ino)
        finally:
            os.close(original_stdout)
            os.close(original_stderr)

    def test_devnull_descriptor_is_closed_after_exit(self) -> None:
        # Count the open file descriptors before and after. The context
        # manager opens one devnull descriptor and two saved descriptors;
        # all three must be closed on exit, so the count should return to
        # its original value.
        def count_open_fds() -> int:
            # ``/proc/self/fd`` is Linux-specific. On other platforms we
            # fall back to a best-effort count using ``os.listdir`` only
            # when the directory exists; otherwise skip the assertion.
            try:
                return len(os.listdir("/proc/self/fd"))
            except OSError:
                return -1

        before = count_open_fds()
        if before == -1:
            self.skipTest("no /proc/self/fd on this platform")
        with redirect_to_devnull():
            pass
        after = count_open_fds()
        self.assertEqual(after, before)

    def test_nested_contexts_restore_outer_redirection(self) -> None:
        # Nesting is allowed even though it is not thread-safe: the inner
        # context saves the devnull descriptor installed by the outer one
        # and restores it on exit. The outer context then restores the
        # original streams.
        original_stdout = os.dup(1)
        try:
            with redirect_to_devnull():
                with redirect_to_devnull():
                    os.write(1, b"inner\n")
                # Still inside the outer context: fd 1 should still be
                # devnull, not the original stdout.
                self.assertNotEqual(os.fstat(1).st_ino, os.fstat(original_stdout).st_ino)
            self.assertEqual(os.fstat(1).st_ino, os.fstat(original_stdout).st_ino)
        finally:
            os.close(original_stdout)

    def test_closed_stdout_raises_oserror(self) -> None:
        # The module docstring promises that a closed standard stream
        # propagates as OSError rather than being silently ignored.
        saved_stdout = os.dup(1)
        try:
            os.close(1)
            with self.assertRaises(OSError):
                with redirect_to_devnull():
                    pass
        finally:
            # Restore fd 1 before the test framework tries to use it.
            os.dup2(saved_stdout, 1)
            os.close(saved_stdout)


if __name__ == "__main__":
    unittest.main()
