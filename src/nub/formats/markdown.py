"""
Markdown format strategy.

Parses Markdown preserving heading hierarchy (H1 > H2 > H3 > ...).
Supports ATX headings (# style) and fenced code blocks.

Note: MIND_MAP.md files use MindMap strategy (detects [N] node markers).
This strategy is for generic .md files without numbered nodes.
"""

from __future__ import annotations

import re

from ..dom import Node
from .base import FormatStrategy, registry

# ATX heading pattern: # to ###### followed by text
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$")

# Fenced code block start/end
CODE_FENCE_PATTERN = re.compile(r"^```")


class MarkdownStrategy(FormatStrategy):
    """Markdown parser preserving heading hierarchy."""

    @property
    def name(self) -> str:
        return "markdown"

    @property
    def extensions(self) -> list[str]:
        return [".md", ".markdown"]

    def parse(self, content: str) -> Node:
        """
        Parse Markdown into tree of nodes.

        Structure:
        - Document (root)
          - H1 nodes (direct children of root)
            - Paragraphs, code blocks
            - H2 nodes (children of H1)
              - Paragraphs, code blocks
              - H3 nodes (children of H2)
                ...
        """
        root = Node(content="", type="document", name="root")

        if not content.strip():
            return root

        lines = content.splitlines()

        # Stack of (level, node) for heading hierarchy
        # Level 0 = root, level 1 = H1, etc.
        heading_stack: list[tuple[int, Node]] = [(0, root)]

        # Current content accumulator (for paragraphs)
        current_para_lines: list[str] = []

        # Code block state
        in_code_block = False
        code_lines: list[str] = []

        def flush_paragraph():
            """Add accumulated paragraph to current heading."""
            nonlocal current_para_lines
            if current_para_lines:
                text = "\n".join(current_para_lines).strip()
                if text:
                    para = Node(content=text, type="paragraph", name=None)
                    _, parent = heading_stack[-1]
                    parent.add_child(para)
                current_para_lines = []

        def flush_code_block():
            """Add accumulated code block to current heading."""
            nonlocal code_lines
            if code_lines:
                code = "\n".join(code_lines)
                code_node = Node(content=code, type="code", name=None, atomic=True)
                _, parent = heading_stack[-1]
                parent.add_child(code_node)
                code_lines = []

        for line in lines:
            # Check for code fence
            if CODE_FENCE_PATTERN.match(line):
                if in_code_block:
                    # End of code block
                    flush_code_block()
                    in_code_block = False
                else:
                    # Start of code block
                    flush_paragraph()
                    in_code_block = True
                continue

            if in_code_block:
                code_lines.append(line)
                continue

            # Check for heading
            heading_match = HEADING_PATTERN.match(line)
            if heading_match:
                flush_paragraph()

                hashes = heading_match.group(1)
                title = heading_match.group(2).strip()
                level = len(hashes)

                # Create heading node
                heading_content = f"{'#' * level} {title}"
                heading_node = Node(
                    content=heading_content,
                    type=f"h{level}",
                    name=title
                )

                # Find appropriate parent (pop stack until we find a lower level)
                while len(heading_stack) > 1 and heading_stack[-1][0] >= level:
                    heading_stack.pop()

                # Add to parent
                _, parent = heading_stack[-1]
                parent.add_child(heading_node)

                # Push onto stack
                heading_stack.append((level, heading_node))
            else:
                # Regular line - accumulate for paragraph
                # Skip empty lines but they signal paragraph breaks
                if line.strip():
                    current_para_lines.append(line)
                elif current_para_lines:
                    flush_paragraph()

        # Flush any remaining content
        if in_code_block:
            flush_code_block()
        else:
            flush_paragraph()

        return root

    def rank(self, node: Node) -> float:
        """
        Return topology score for Markdown node.

        Heading hierarchy prioritized, code blocks preserved.
        """
        type_scores = {
            "h1": 0.9,
            "h2": 0.8,
            "h3": 0.7,
            "h4": 0.6,
            "h5": 0.6,
            "h6": 0.6,
            "code": 0.6,
            "paragraph": 0.5,
            "document": 0.5,
        }
        return type_scores.get(node.type, 0.5)

    def render(self, node: Node, budget: int) -> str | None:
        """
        LOD renderer for Markdown nodes.

        - Full content when budget allows
        - Heading line only when tight (for heading nodes)
        - Truncate with ellipsis for paragraphs
        - Code blocks: full or fold (no mid-truncation due to atomic=True)
        """
        if budget <= 0:
            return None

        content = node.content
        content_len = len(content)

        # Full content fits
        if content_len <= budget:
            return content

        # For headings: show just the heading line when tight
        if node.type.startswith("h") and node.name:
            level = int(node.type[1])
            heading_line = f"{'#' * level} {node.name}"
            if len(heading_line) <= budget:
                return heading_line
            # Heading line doesn't fit - truncate it
            if budget >= 4:
                return heading_line[:budget - 3] + "..."
            return None

        # For code blocks (atomic): full or fold
        if node.type == "code" or node.atomic:
            return None  # Don't mid-truncate code

        # For paragraphs: truncate with ellipsis
        if budget >= 4:
            return content[:budget - 3] + "..."

        return None


# Register the strategy
registry.register(MarkdownStrategy())
