"""Promotion-grade study capsule: a frozen StudySpec plus immutable receipts.

Task selection, arms, repetitions, model, revision, validity, score provenance,
and authoritative SDK usage all key on one stable trial identity, so nothing
downstream has to infer a study's scientific identity from a filesystem path.
"""

from __future__ import annotations

from .capsule import AllAttempts, PairedValid, StudyCapsule
from .errors import (
    CapsuleError,
    CapsuleIntegrityError,
    CompletenessError,
    ReceiptError,
    SpecError,
)
from .hashing import content_hash, file_hash
from .receipt import (
    RECEIPT_SCHEMA_VERSION,
    STATUS_INELIGIBLE,
    STATUS_INFRA_INVALID,
    STATUS_VALID,
    TrialReceipt,
    TrialUsage,
    append_receipt,
    is_zero_cost_pre_agent_mcp_failure,
    read_receipts,
)
from .spec import (
    ATTEMPT_POLICIES,
    SPEC_SCHEMA_VERSION,
    TOKEN_SOURCES,
    Arm,
    StudySpec,
    TrialID,
)

__all__ = [
    "ATTEMPT_POLICIES",
    "AllAttempts",
    "Arm",
    "CapsuleError",
    "CapsuleIntegrityError",
    "CompletenessError",
    "PairedValid",
    "RECEIPT_SCHEMA_VERSION",
    "ReceiptError",
    "SPEC_SCHEMA_VERSION",
    "STATUS_INELIGIBLE",
    "STATUS_INFRA_INVALID",
    "STATUS_VALID",
    "SpecError",
    "StudyCapsule",
    "StudySpec",
    "TOKEN_SOURCES",
    "TrialID",
    "TrialReceipt",
    "TrialUsage",
    "append_receipt",
    "content_hash",
    "file_hash",
    "is_zero_cost_pre_agent_mcp_failure",
    "read_receipts",
]
