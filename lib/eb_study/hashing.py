"""Content hashing for study artifacts.

One canonicalization, used by the spec hash, the task-manifest hash, and every
artifact digest. Separate module so a future change to the encoding cannot be
made on one side of a comparison only.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def canonical_json(payload: Any) -> str:
    """Encode ``payload`` so equal content always yields equal bytes."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload: Any) -> str:
    """sha256 of the canonical encoding of ``payload``, hex, ``sha256:`` prefixed."""

    digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def file_hash(path: Path) -> str:
    """sha256 of a file's bytes, ``sha256:`` prefixed.

    Bytes, not parsed content: this is used for artifacts and traces whose
    formats the capsule does not own.
    """

    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
    return f"sha256:{digest}"
