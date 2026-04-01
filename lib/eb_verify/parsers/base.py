"""
Abstract base for language-specific source parsers.

All language parsers (Python, Go, etc.) implement the LanguageParser
protocol so verification code can work across languages.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ImportInfo:
    """A single import statement."""

    module: str
    name: str | None = None
    alias: str | None = None
    line: int = 0
    level: int = 0  # 0 = absolute, 1+ = relative


@dataclass(frozen=True)
class SymbolInfo:
    """A symbol definition (function, class, variable, method)."""

    name: str
    kind: str  # "function", "class", "variable", "method"
    line: int = 0


@dataclass(frozen=True)
class Reference:
    """A reference to a symbol (usage site, not definition)."""

    name: str
    line: int
    col: int = 0


class LanguageParser(Protocol):
    """Protocol for language-specific source code parsers."""

    language: str

    def extract_imports(self, source: str) -> list[ImportInfo]: ...

    def extract_symbols(self, source: str) -> list[SymbolInfo]: ...

    def find_symbol_references(
        self, source: str, symbol_name: str
    ) -> list[Reference]: ...
