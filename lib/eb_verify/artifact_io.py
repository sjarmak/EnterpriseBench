"""Workspace-safe artifact reading.

The primitive every artifact consumer shares: read a file only after proving the
path stays inside the workspace. It lives below both the plugin registry and the
verifier primitives (groundedness) because both need it and neither may depend on
the other -- ``groundedness`` reaching up into ``eb_verify.plugins`` for ``safe_read``
is what closed the groundedness -> plugins -> incident_report -> groundedness cycle.

Stdlib only, by design. Anything imported here is paid by every validator.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


class FileTooLargeError(ValueError):
    """Raised by safe_read when a file exceeds the caller's max_bytes cap."""


# Default cap for every safe_read call (opt out with max_bytes=None). Generous
# relative to the hand-authored JSON/text artifacts (answer, incident report,
# etc.) that are meant to be at most a few KB; this bounds worst-case memory use
# if a symlink (or literal file) at the artifact path targets something huge.
MAX_ARTIFACT_BYTES = 10 * 1024 * 1024  # 10 MiB


def safe_read(
    path: Path, workspace: Path, max_bytes: Optional[int] = MAX_ARTIFACT_BYTES
) -> str:
    """Read a file, asserting the resolved path stays within workspace (symlink-safe).

    Defaults to capping reads at MAX_ARTIFACT_BYTES so callers are protected
    unless they explicitly opt into unbounded reads with max_bytes=None. When
    max_bytes is set, files larger than the cap raise FileTooLargeError
    without being read. Containment is checked FIRST: an escaping path always
    reports the escape and is never stat'd for a size verdict.

    Opens *path* once via a file descriptor and derives the real path,
    containment check, size check, and read all from that same fd (rather
    than re-resolving/re-opening the path at each step). This closes the
    TOCTOU window a path-based resolve-then-reopen sequence would leave
    between the containment check and the read.
    """
    workspace_resolved = workspace.resolve()
    fd = os.open(str(path), os.O_RDONLY)
    with os.fdopen(fd) as handle:
        real_path = Path(os.path.realpath(f"/proc/self/fd/{fd}"))
        if not str(real_path).startswith(str(workspace_resolved) + "/") and real_path != workspace_resolved:
            raise ValueError(
                f"Path escapes workspace: {path} -> {real_path}"
            )
        if max_bytes is not None:
            size = os.fstat(fd).st_size
            if size > max_bytes:
                raise FileTooLargeError(
                    f"File too large to read: {path} is {size} bytes (max {max_bytes})"
                )
        return handle.read()
