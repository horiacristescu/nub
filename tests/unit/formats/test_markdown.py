"""
Unit tests for Markdown format strategy.
"""

import pytest
from pathlib import Path
from nub.dom import Node
from nub.formats.markdown import MarkdownStrategy


class TestMarkdownParsing:
    """Test Markdown parsing into tree structure."""

    @pytest.fixture
    def strategy(self):
        return MarkdownStrategy()

    def test_parse_empty(self, strategy):
        """Empty content returns document with no children."""
        root = strategy.parse("")
        assert root.type == "document"
        assert root.children == []

    def test_parse_single_heading(self, strategy):
        """Single H1 creates one heading child."""
        root = strategy.parse("# Title")
        assert len(root.children) == 1
        assert root.children[0].type == "h1"
        assert root.children[0].name == "Title"

    def test_parse_heading_hierarchy(self, strategy):
        """H1 > H2 > H3 nesting is correct."""
        content = """# Main
## Sub
### Deep
"""
        root = strategy.parse(content)

        # H1 at root level
        assert len(root.children) == 1
        h1 = root.children[0]
        assert h1.type == "h1"
        assert h1.name == "Main"

        # H2 is child of H1
        assert len(h1.children) == 1
        h2 = h1.children[0]
        assert h2.type == "h2"
        assert h2.name == "Sub"

        # H3 is child of H2
        assert len(h2.children) == 1
        h3 = h2.children[0]
        assert h3.type == "h3"
        assert h3.name == "Deep"

    def test_parse_multiple_h1(self, strategy):
        """Multiple H1s are siblings at root level."""
        content = """# First
# Second
"""
        root = strategy.parse(content)
        assert len(root.children) == 2
        assert root.children[0].name == "First"
        assert root.children[1].name == "Second"

    def test_parse_h2_without_h1(self, strategy):
        """H2 without H1 parent attaches to root."""
        content = """## Orphan Section
Some content
"""
        root = strategy.parse(content)
        assert len(root.children) == 1
        assert root.children[0].type == "h2"
        assert root.children[0].name == "Orphan Section"

    def test_parse_paragraph_under_heading(self, strategy):
        """Paragraphs become children of their heading."""
        content = """# Title
This is a paragraph.

Another paragraph.
"""
        root = strategy.parse(content)
        h1 = root.children[0]

        # Should have paragraph children
        paras = [c for c in h1.children if c.type == "paragraph"]
        assert len(paras) >= 1
        assert "This is a paragraph" in paras[0].content

    def test_parse_code_block_atomic(self, strategy):
        """Code blocks are marked atomic."""
        content = """# Code Example
```python
def foo():
    pass
```
"""
        root = strategy.parse(content)
        h1 = root.children[0]

        # Find code block child
        code_blocks = [c for c in h1.children if c.type == "code"]
        assert len(code_blocks) == 1
        assert code_blocks[0].atomic is True
        assert "def foo():" in code_blocks[0].content

    def test_parse_code_block_with_language(self, strategy):
        """Code blocks preserve content without fence markers."""
        content = """# Example
```bash
npm install
```
"""
        root = strategy.parse(content)
        h1 = root.children[0]
        code = [c for c in h1.children if c.type == "code"][0]

        # Should contain the code, not the fence markers
        assert "npm install" in code.content
        assert "```" not in code.content

    def test_parse_preserves_heading_level_in_type(self, strategy):
        """Heading level is captured in node type."""
        content = """# H1
## H2
### H3
#### H4
##### H5
###### H6
"""
        root = strategy.parse(content)

        def find_types(node, types=None):
            if types is None:
                types = []
            if node.type.startswith("h"):
                types.append(node.type)
            for c in node.children:
                find_types(c, types)
            return types

        types = find_types(root)
        assert "h1" in types
        assert "h2" in types
        assert "h3" in types
        assert "h4" in types
        assert "h5" in types
        assert "h6" in types


class TestMarkdownRanking:
    """Test topology scoring for Markdown nodes."""

    @pytest.fixture
    def strategy(self):
        return MarkdownStrategy()

    def test_rank_h1_highest(self, strategy):
        """H1 gets highest score (0.9)."""
        node = Node(content="# Title", type="h1", name="Title")
        assert strategy.rank(node) == 0.9

    def test_rank_h2(self, strategy):
        """H2 gets 0.8."""
        node = Node(content="## Section", type="h2", name="Section")
        assert strategy.rank(node) == 0.8

    def test_rank_h3(self, strategy):
        """H3 gets 0.7."""
        node = Node(content="### Subsection", type="h3", name="Subsection")
        assert strategy.rank(node) == 0.7

    def test_rank_h4_h6(self, strategy):
        """H4-H6 get 0.6."""
        for level in ["h4", "h5", "h6"]:
            node = Node(content=f"{'#' * int(level[1])} Heading", type=level, name="Heading")
            assert strategy.rank(node) == 0.6

    def test_rank_code_block(self, strategy):
        """Code blocks get 0.6."""
        node = Node(content="def foo():", type="code", name=None)
        assert strategy.rank(node) == 0.6

    def test_rank_paragraph(self, strategy):
        """Paragraphs get 0.5."""
        node = Node(content="Some text.", type="paragraph", name=None)
        assert strategy.rank(node) == 0.5

    def test_rank_h1_over_paragraph(self, strategy):
        """H1 ranked higher than paragraph."""
        h1 = Node(content="# Title", type="h1", name="Title")
        para = Node(content="Some text.", type="paragraph", name=None)
        assert strategy.rank(h1) > strategy.rank(para)


class TestMarkdownLOD:
    """Test Level of Detail rendering."""

    @pytest.fixture
    def strategy(self):
        return MarkdownStrategy()

    def test_render_full_when_budget_sufficient(self, strategy):
        """Full content when budget allows."""
        node = Node(content="## Features\n\nList of features.", type="h2", name="Features")
        result = strategy.render(node, budget=100)
        assert result == node.content

    def test_render_heading_only_when_tight(self, strategy):
        """Just heading line when budget tight."""
        node = Node(
            content="## Very Long Section Title\n\nLots of content here that won't fit.",
            type="h2",
            name="Very Long Section Title"
        )
        # Budget fits heading but not content
        result = strategy.render(node, budget=30)
        assert result == "## Very Long Section Title"

    def test_render_none_when_too_small(self, strategy):
        """Returns None when budget too small."""
        node = Node(content="## Section", type="h2", name="Section")
        result = strategy.render(node, budget=0)
        assert result is None

    def test_render_paragraph_truncates(self, strategy):
        """Paragraphs truncate with ellipsis."""
        node = Node(
            content="This is a very long paragraph that should be truncated.",
            type="paragraph",
            name=None
        )
        result = strategy.render(node, budget=20)
        assert result is not None
        assert len(result) <= 20
        assert result.endswith("...")

    def test_render_code_block_full_or_fold(self, strategy):
        """Code blocks either show full or fold (no mid-truncation)."""
        code = "def foo():\n    return 42"
        node = Node(content=code, type="code", name=None, atomic=True)

        # Large budget: full code
        result = strategy.render(node, budget=100)
        assert result == code

        # Small budget: should fold (None)
        result_small = strategy.render(node, budget=5)
        assert result_small is None

    def test_render_progressive_degradation(self, strategy):
        """Detail decreases as budget decreases."""
        content = "## Installation\n\nRun the install command to set up."
        node = Node(content=content, type="h2", name="Installation")

        # Large: full
        full = strategy.render(node, budget=100)
        assert full == content

        # Medium: heading only
        medium = strategy.render(node, budget=20)
        assert medium == "## Installation"

        # Tiny: fold
        tiny = strategy.render(node, budget=3)
        assert tiny is None or len(tiny) <= 3


class TestMarkdownIntegration:
    """Integration tests with fixture files."""

    @pytest.fixture
    def strategy(self):
        return MarkdownStrategy()

    def test_parse_readme_sample_fixture(self, strategy):
        """Parse the readme_sample.md fixture correctly."""
        fixture_path = Path(__file__).parent.parent.parent / "fixtures" / "readme_sample.md"
        content = fixture_path.read_text()

        root = strategy.parse(content)

        # Should have parsed structure
        assert root.type == "document"
        assert len(root.children) > 0

        # First child should be H1 "Project Title"
        h1 = root.children[0]
        assert h1.type == "h1"
        assert h1.name == "Project Title"

        # Should have H2 children (Features, Installation, etc.)
        h2_names = [c.name for c in h1.children if c.type == "h2"]
        assert "Features" in h2_names
        assert "Installation" in h2_names

    def test_registry_detection(self, strategy):
        """Markdown files detected by extension."""
        from nub.formats.base import registry

        # Should detect .md extension
        result = registry.detect("# Test", "test.md")
        assert result is not None
        assert result.strategy.name == "markdown"
