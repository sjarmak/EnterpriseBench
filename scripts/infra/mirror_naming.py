#!/usr/bin/env python3
"""Single source of truth for the sg-evals mirror-naming convention.

Extracted from create_sg_mirrors.py, where this formula previously lived
inline and had drifted into 5 independent copies across the codebase
(create_sg_mirrors.py, dockerfile_generator.py, mcp/sourcegraph.py,
generate_sg_index.py, validate_tasks_preflight.py) — see
EnterpriseBench-k9po. Behavior is unchanged from the original; only its
location moved.
"""

import re

ORG = "sg-evals"

# A real mirror's name segment (after the "sg-evals/" prefix), e.g.
# "ansible--v2.16.0". Matches the validation create_sg_mirrors.py applies
# before ever creating a mirror on GitHub.
GITHUB_REPO_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+-[a-zA-Z0-9._-]+$")


def is_hex_rev(rev: str) -> bool:
    """True if rev looks like a raw git hash (all hex chars), not a tag.

    An unresolved git-parent-notation rev like "<sha>~1" is NOT hex (the
    "~" isn't a hex char) and so is classified as a tag here — callers that
    feed such a rev straight into a mirror name get an unrepresentable
    GitHub name (EnterpriseBench-k9po). Resolve to a concrete SHA before
    calling anything that uses this.
    """
    return all(c in "0123456789abcdef" for c in rev.lower())


def derive_mirror_name(repo_url_or_path: str, rev: str) -> str:
    """Return the sg-evals mirror name for a repo pinned at rev.

    repo_url_or_path may be a full URL ("https://github.com/org/repo.git"),
    a scheme-less path ("github.com/org/repo"), or a bare "org/repo" — only
    the final path segment (the repo name) is used; the org is dropped, to
    match what create_sg_mirrors.py actually names mirrors on GitHub.
    """
    upstream = (
        repo_url_or_path.replace("https://", "").replace("http://", "").rstrip("/")
    )
    if upstream.endswith(".git"):
        upstream = upstream[:-4]
    repo_name = upstream.split("/")[-1]

    ref_suffix = rev[:8] if is_hex_rev(rev) else rev
    ref_suffix = ref_suffix.replace("/", "_")

    return f"{ORG}/{repo_name}--{ref_suffix}"
