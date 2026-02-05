"""
CSV format strategy.

TODO: Implement CSV parsing preserving header row.
Samples rows using head/tail strategy with uniform stride.
"""

from ..dom import Node
from .base import FormatStrategy


class CSVStrategy(FormatStrategy):
    """CSV parser strategy."""

    @property
    def name(self) -> str:
        return "csv"

    @property
    def extensions(self) -> list[str]:
        return [".csv", ".tsv"]

    def parse(self, content: str) -> Node:
        """Parse CSV into tree of nodes."""
        # TODO: Implement CSV parsing
        return Node(content=content, type="document", name="root")

    def rank(self, node: Node) -> float:
        """Return topology score for CSV node."""
        # TODO: Implement topology scoring
        return 0.5


def parse_csv_rows(content: str) -> Node:
    """Parse CSV rows (helper function)."""
    # TODO: Implement
    return Node(content=content, type="document", name="root")
