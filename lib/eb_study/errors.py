"""Failure types for the study capsule.

One exception per boundary the capsule is allowed to fail at, so a caller can
tell "this file is not a spec" from "this run is missing an arm" without
matching on message text. Everything here is fatal: the capsule has no
degraded mode, because a partially-trusted study is exactly the artifact this
package exists to make unpublishable.
"""

from __future__ import annotations


class CapsuleError(Exception):
    """Base for every study-capsule failure."""


class SpecError(CapsuleError):
    """The StudySpec is absent, malformed, or missing a frozen field."""


class ReceiptError(CapsuleError):
    """A trial receipt is malformed, or claims provenance it does not carry."""


class CapsuleIntegrityError(CapsuleError):
    """A receipt does not belong to the spec it was loaded against."""


class CompletenessError(CapsuleError):
    """A declared arm or repetition has no valid receipt.

    Raised rather than dropping the arm: a two-arm table produced from a
    three-arm study reads as a valid result, and nothing in it says an arm
    is gone.
    """
