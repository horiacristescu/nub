"""
Conversation format strategy.

TODO: Implement conversation log parsing chunking by message turns.
Preserves system prompt, first query, final resolution.
Folds intermediate debugging loops.
"""

from ..dom import Node
from .base import FormatStrategy


class ConversationStrategy(FormatStrategy):
    """Conversation log parser strategy."""

    @property
    def name(self) -> str:
        return "conversation"

    @property
    def extensions(self) -> list[str]:
        return [".jsonl", ".chat"]

    def parse(self, content: str) -> Node:
        """Parse conversation log into tree of nodes."""
        # TODO: Implement conversation parsing
        return Node(content=content, type="document", name="root")

    def rank(self, node: Node) -> float:
        """Return topology score for conversation node."""
        # TODO: Implement topology scoring
        return 0.5


def parse_conversation_turns(content: str) -> Node:
    """Parse conversation turns (helper function)."""
    # TODO: Implement
    return Node(content=content, type="document", name="root")

