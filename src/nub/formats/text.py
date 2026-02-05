"""
Text format strategy.

Parses text into a 2-level tree: sections (separated by blank lines) containing lines.
This allows hierarchical compression - drop entire sections or lines within sections.
"""

import re

from ..config import get_config
from ..dom import Node
from .base import FormatStrategy, registry


class TextStrategy(FormatStrategy):
    """Plain text as sections of lines, split on blank lines."""

    @property
    def name(self) -> str:
        return "text"

    @property
    def extensions(self) -> list[str]:
        return [".txt", ".text", ".log"]

    def parse(self, content: str) -> Node:
        """
        Parse into tree: root -> sections -> lines.
        Sections are separated by one or more blank lines.
        """
        root = Node(content="", type="document", name="root")

        if not content:
            return root

        lines = content.splitlines()

        # Group lines into sections (split on blank lines)
        sections: list[list[tuple[int, str]]] = []
        current_section: list[tuple[int, str]] = []

        for i, line in enumerate(lines):
            if line.strip() == "":
                if current_section:
                    sections.append(current_section)
                    current_section = []
            else:
                current_section.append((i + 1, line))  # 1-indexed

        if current_section:
            sections.append(current_section)

        # Build tree
        for sec_idx, section_lines in enumerate(sections):
            if not section_lines:
                continue

            first_line_num = section_lines[0][0]
            last_line_num = section_lines[-1][0]

            section_node = Node(
                content="",
                type="section",
                name=f"S{sec_idx + 1}:L{first_line_num}-{last_line_num}"
            )

            for line_num, line_content in section_lines:
                line_node = Node(
                    content=line_content,
                    type="line",
                    name=f"L{line_num}"
                )
                section_node.add_child(line_node)

            root.add_child(section_node)

        return root

    def rank(self, node: Node) -> float:
        """Topology scores from config."""
        cfg = get_config().text
        if node.type == "section":
            return cfg.section_score
        return cfg.line_score


class CustomSeparatorStrategy(FormatStrategy):
    """Text format with custom separator for chunking."""

    def __init__(self, separator: str | None = None, separator_regex: str | None = None):
        """
        Initialize with custom separator.

        Args:
            separator: Literal string to split on (e.g., "---")
            separator_regex: Regex pattern to split on (e.g., r"^---$")
        """
        self._separator = separator
        self._separator_regex = separator_regex

    @property
    def name(self) -> str:
        return "text-custom"

    @property
    def extensions(self) -> list[str]:
        return []  # Not registered by extension

    def parse(self, content: str) -> Node:
        """
        Parse into tree: root -> chunks.
        Chunks are separated by custom separator instead of blank lines.
        """
        root = Node(content="", type="document", name="root")

        if not content:
            return root

        # Split by custom separator
        if self._separator_regex:
            # Use regex split
            try:
                chunks = re.split(self._separator_regex, content, flags=re.MULTILINE)
            except re.error:
                # Fallback to newline on bad regex
                chunks = content.split("\n")
        elif self._separator:
            # Use literal string split
            chunks = content.split(self._separator)
        else:
            # Fallback to newline
            chunks = content.split("\n")

        # Build tree - each chunk becomes a direct child
        for chunk_idx, chunk_content in enumerate(chunks):
            if not chunk_content.strip():
                continue

            chunk_node = Node(
                content=chunk_content,
                type="chunk",
                name=f"C{chunk_idx + 1}"
            )
            root.add_child(chunk_node)

        return root

    def rank(self, node: Node) -> float:
        """Topology scores from config."""
        cfg = get_config().text
        # Chunks are like sections
        if node.type == "chunk":
            return cfg.section_score
        return cfg.line_score


# Register the default strategy
registry.register(TextStrategy())
