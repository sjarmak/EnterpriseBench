"""
Language parser registry for source code analysis.

Parsers extract imports, symbols, and dependency graphs from source files.
Each language parser implements the LanguageParser protocol.
"""

from __future__ import annotations

from typing import Dict, Optional

from eb_verify.parsers.base import LanguageParser

# Parser registry — keyed by language name
_registry: Dict[str, LanguageParser] = {}


def register_parser(parser: LanguageParser) -> None:
    """Register a language parser."""
    _registry[parser.language] = parser


def get_parser(language: str) -> Optional[LanguageParser]:
    """Get a parser by language name."""
    return _registry.get(language)


def list_parsers() -> list[str]:
    """List registered parser language names."""
    return list(_registry.keys())


# Import parsers to trigger registration
from eb_verify.parsers.python_ast import PythonASTParser  # noqa: E402
from eb_verify.parsers.go_ast import GoParser  # noqa: E402

register_parser(PythonASTParser())
register_parser(GoParser())
