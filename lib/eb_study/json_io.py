"""Strict JSON decoding for immutable study and publication boundaries."""

from __future__ import annotations

import json
from typing import Any


def strict_json_loads(source: str) -> Any:
    """Decode JSON without silently accepting duplicate keys or NaN values."""

    return json.loads(
        source,
        object_pairs_hook=_unique_object,
        parse_constant=_reject_nonfinite,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ValueError(f"non-finite JSON number: {value}")
