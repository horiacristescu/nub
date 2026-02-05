"""
Base format interface and registry.

Each format strategy implements this interface to handle a specific content type.
The registry manages format detection and selection.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ..dom import Node


class FormatStrategy(ABC):
    """Base class for content format handlers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable format name."""
        ...

    @property
    @abstractmethod
    def extensions(self) -> list[str]:
        """File extensions this format handles (e.g., ['.txt', '.text'])."""
        ...

    def detect(self, content: str) -> bool:
        """
        Magic detection: returns True if content looks like this format.
        Default implementation returns False (rely on extension only).
        """
        return False

    @abstractmethod
    def parse(self, content: str) -> Node:
        """
        Parse content into a tree of Nodes.
        Returns the root node of the tree.
        """
        ...

    def rank(self, node: Node) -> float:
        """
        Return topology score for a node (0.0 to 1.0).
        Default: 0.5 (neutral importance).
        """
        return 0.5

    def render(self, node: Node, budget: int) -> str | None:
        """
        Render node at appropriate detail level for budget.

        Progressive LOD: as budget decreases, show less detail rather than
        truncating. Returns None if budget is too small for any useful output
        (node should be folded into count).

        Default implementation: truncate content. Override in subclasses for
        semantic degradation (e.g., signature → name for code).
        """
        if budget <= 0:
            return None
        # Default: just truncate (no semantic degradation)
        content = node.content
        if len(content) <= budget:
            return content
        # Simple truncation with ellipsis
        if budget <= 3:
            return None  # Too small for anything useful
        return content[:budget - 3] + "..."


@dataclass
class FormatMatch:
    """Result of format detection."""
    strategy: FormatStrategy
    confidence: float  # 0.0 to 1.0


class FormatRegistry:
    """Registry of format strategies with detection and selection."""

    def __init__(self):
        self._strategies: list[FormatStrategy] = []
        self._by_extension: dict[str, FormatStrategy] = {}
        self._by_name: dict[str, FormatStrategy] = {}

    def register(self, strategy: FormatStrategy) -> None:
        """Register a format strategy."""
        self._strategies.append(strategy)
        self._by_name[strategy.name] = strategy
        for ext in strategy.extensions:
            # First registered wins for extension conflicts
            if ext not in self._by_extension:
                self._by_extension[ext] = strategy

    def get_by_name(self, name: str) -> FormatStrategy | None:
        """Get strategy by name (for --type override)."""
        return self._by_name.get(name)

    def get_by_extension(self, ext: str) -> FormatStrategy | None:
        """Get strategy by file extension."""
        # Normalize extension
        if not ext.startswith('.'):
            ext = '.' + ext
        return self._by_extension.get(ext.lower())

    def detect(self, content: str, filename: str | None = None) -> FormatMatch | None:
        """
        Detect the best format for content.

        Priority:
        1. Extension match (high confidence)
        2. Magic detection (medium confidence)
        3. Fallback to text (low confidence)
        """
        # Try extension first
        if filename:
            ext = self._get_extension(filename)
            if ext and ext in self._by_extension:
                return FormatMatch(
                    strategy=self._by_extension[ext],
                    confidence=1.0
                )

        # Try magic detection
        for strategy in self._strategies:
            if strategy.detect(content):
                return FormatMatch(
                    strategy=strategy,
                    confidence=0.8
                )

        # Return None to let caller decide fallback
        return None

    def _get_extension(self, filename: str) -> str | None:
        """Extract lowercase extension from filename."""
        if '.' in filename:
            return '.' + filename.rsplit('.', 1)[-1].lower()
        return None

    @property
    def strategies(self) -> list[FormatStrategy]:
        """List all registered strategies."""
        return list(self._strategies)


# Global registry instance
registry = FormatRegistry()
