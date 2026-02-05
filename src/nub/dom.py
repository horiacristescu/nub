"""
DOM - Document Object Model for Nub

Unified representation for all parsed content. Every content type produces
a tree of Nodes. Links connect named nodes to form graphs when needed.

Key invariant: Only named nodes can be link targets. Anonymous nodes exist
only as tree children.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field


@dataclass
class Node:
    """A node in the content tree."""
    content: str
    type: str = "text"
    name: str | None = None
    children: list[Node] = field(default_factory=list)
    atomic: bool = False  # If True, content is pre-optimized - only tail-truncate, never middle-drop
    source_line: int | None = None  # Source file line number (for structured formats)

    @property
    def is_named(self) -> bool:
        """Only named nodes can be link targets."""
        return self.name is not None

    def depth_first(self) -> Iterator[Node]:
        """Traverse tree depth-first, yielding self then children."""
        yield self
        for child in self.children:
            yield from child.depth_first()

    def breadth_first(self) -> Iterator[Node]:
        """Traverse tree breadth-first."""
        queue: list[Node] = [self]
        while queue:
            node = queue.pop(0)
            yield node
            queue.extend(node.children)

    def add_child(self, child: Node) -> Node:
        """Add a child node and return it for chaining."""
        self.children.append(child)
        return child


@dataclass
class Link:
    """A directional edge between two named nodes."""
    source: Node
    target: Node

    def __post_init__(self):
        if not self.source.is_named:
            raise ValueError(f"Link source must be named, got anonymous node with content: {self.source.content[:50]!r}")
        if not self.target.is_named:
            raise ValueError(f"Link target must be named, got anonymous node with content: {self.target.content[:50]!r}")


def find_named(root: Node, name: str) -> Node | None:
    """Find a named node in the tree."""
    for node in root.depth_first():
        if node.name == name:
            return node
    return None


def collect_named(root: Node) -> dict[str, Node]:
    """Collect all named nodes into a lookup dict."""
    return {node.name: node for node in root.depth_first() if node.name is not None}
