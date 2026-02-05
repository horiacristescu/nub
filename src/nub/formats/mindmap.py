"""
Mind Map format strategy.

Parses mind map files where nodes are marked with [N] prefixes.
Each [N] node becomes a named section that can be compressed independently.
"""

import re

from ..config import get_config
from ..dom import Node
from .base import FormatStrategy, registry


class MindMapStrategy(FormatStrategy):
    """Mind map parser treating [N] markers as section boundaries."""

    @property
    def name(self) -> str:
        return "mindmap"

    @property
    def extensions(self) -> list[str]:
        return []  # Detected by content, not extension

    def detect(self, content: str) -> bool:
        """
        Detect mind map format by looking for [N] node markers.

        Heuristic: If we see multiple lines starting with [N] patterns, it's likely a mind map.
        """
        node_pattern = re.compile(r'^\[\d+\]', re.MULTILINE)
        matches = node_pattern.findall(content)
        return len(matches) >= 3  # At least 3 nodes to be a mind map

    def parse(self, content: str) -> Node:
        """
        Parse into tree: root -> node sections -> lines within each node.

        Structure:
        - Root document
          - Node [1] (section)
            - Line 1 of node content
            - Line 2 of node content
          - Node [2] (section)
            - ...
        """
        root = Node(content="", type="document", name="root")

        if not content:
            return root

        lines = content.splitlines()

        # Pattern to detect node boundaries: [N] Title
        node_pattern = re.compile(r'^\[(\d+)\]\s*(.*)')

        current_node: Node | None = None
        current_node_lines: list[tuple[int, str]] = []
        preamble_lines: list[tuple[int, str]] = []  # Lines before first node

        for i, line in enumerate(lines):
            match = node_pattern.match(line)

            if match:
                # Save previous node if exists
                if current_node and current_node_lines:
                    self._add_lines_to_node(current_node, current_node_lines)
                    root.add_child(current_node)
                    current_node_lines = []

                # Create preamble section if we have preamble lines
                if not current_node and preamble_lines:
                    preamble_node = Node(
                        content="",
                        type="section",
                        name="preamble"
                    )
                    self._add_lines_to_node(preamble_node, preamble_lines)
                    root.add_child(preamble_node)
                    preamble_lines = []

                # Start new node
                node_id = match.group(1)
                match.group(2).strip()

                current_node = Node(
                    content="",
                    type="section",
                    name=f"[{node_id}]"
                )

                # Add the title line itself as first line of node
                current_node_lines.append((i + 1, line))
            else:
                # Add line to current context
                if current_node is not None:
                    current_node_lines.append((i + 1, line))
                else:
                    preamble_lines.append((i + 1, line))

        # Save final node
        if current_node and current_node_lines:
            self._add_lines_to_node(current_node, current_node_lines)
            root.add_child(current_node)

        # Handle case where there was only preamble
        if not current_node and preamble_lines:
            preamble_node = Node(
                content="",
                type="section",
                name="preamble"
            )
            self._add_lines_to_node(preamble_node, preamble_lines)
            root.add_child(preamble_node)

        return root

    def _add_lines_to_node(self, section_node: Node, lines: list[tuple[int, str]]):
        """Add line children to a section node."""
        for line_num, line_content in lines:
            line_node = Node(
                content=line_content,
                type="line",
                name=f"L{line_num}"
            )
            section_node.add_child(line_node)

    def rank(self, node: Node) -> float:
        """
        Topology scores: sections (nodes) are more important than lines.

        This ensures nodes are preserved even under heavy compression.
        """
        cfg = get_config().text  # Reuse text config
        if node.type == "section":
            return cfg.section_score * 1.5  # Boost nodes higher than text sections
        return cfg.line_score


registry.register(MindMapStrategy())

