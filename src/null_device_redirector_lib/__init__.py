"""Public API for null_device_redirector_lib.

Re-exports the single context manager so callers can import it from the
package root. Keeping the surface tiny makes the intended usage obvious
and avoids accidental coupling to internal helpers.
"""

from .core import redirect_to_devnull

__all__ = ["redirect_to_devnull"]
