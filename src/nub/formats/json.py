"""
JSON format strategy.

TODO: Implement JSON parsing preserving schema structure.
Always keeps top-level keys. Samples arrays (head/tail).
"""

from ..dom import Node
from .base import FormatStrategy


class JSONStrategy(FormatStrategy):
    """JSON parser strategy."""

    @property
    def name(self) -> str:
        return "json"

    @property
    def extensions(self) -> list[str]:
        return [".json"]

    def parse(self, content: str) -> Node:
        """Parse JSON into tree of nodes."""
        # TODO: Implement JSON parsing
        return Node(content=content, type="document", name="root")

    def rank(self, node: Node) -> float:
        """Return topology score for JSON node."""
        # TODO: Implement topology scoring
        return 0.5


def parse_json_tree(content: str) -> Node:
    """Parse JSON tree (helper function)."""
    # TODO: Implement
    return Node(content=content, type="document", name="root")
