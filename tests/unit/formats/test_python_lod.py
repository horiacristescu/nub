"""Tests for Python progressive LOD rendering."""

import pytest
from nub.dom import Node
from nub.formats.python import PythonStrategy


class TestPythonProgressiveLOD:
    """Test progressive Level of Detail rendering."""

    @pytest.fixture
    def strategy(self):
        return PythonStrategy()

    def test_render_full_content_when_budget_sufficient(self, strategy):
        """Full signature shown when budget is large enough."""
        node = Node(
            content="def foo(self, x: int) -> str:",
            type="method",
            name="foo"
        )
        result = strategy.render(node, budget=100)
        assert result == "def foo(self, x: int) -> str:"

    def test_render_name_only_when_budget_tight(self, strategy):
        """Name only shown when budget is too small for signature."""
        node = Node(
            content="def foo(self, x: int, y: str, z: float) -> Result:",
            type="method",
            name="foo"
        )
        # Budget too small for full signature but enough for name
        result = strategy.render(node, budget=10)
        assert result == "foo"

    def test_render_none_when_budget_tiny(self, strategy):
        """Returns None when budget too small for even name."""
        node = Node(
            content="def very_long_method_name(self) -> str:",
            type="method",
            name="very_long_method_name"
        )
        # Budget smaller than name length
        result = strategy.render(node, budget=5)
        # Should truncate name with ellipsis
        assert result == "ve..."

    def test_render_none_when_budget_zero(self, strategy):
        """Returns None when budget is zero."""
        node = Node(content="def foo():", type="function", name="foo")
        result = strategy.render(node, budget=0)
        assert result is None

    def test_render_class_name_only(self, strategy):
        """Class rendered as name when budget tight."""
        node = Node(
            content="class MyVeryLongClassName(BaseClass, Mixin):\n    '''Docstring'''",
            type="class",
            name="MyVeryLongClassName"
        )
        result = strategy.render(node, budget=25)
        assert result == "MyVeryLongClassName"

    def test_render_import_summary_truncated(self, strategy):
        """Import summary truncated appropriately."""
        node = Node(
            content="[58 imports, lines 12-200]",
            type="import_summary",
            name="imports"
        )
        result = strategy.render(node, budget=15)
        assert result.endswith("...")
        assert len(result) <= 15

    def test_progressive_degradation(self, strategy):
        """Verify detail decreases as budget decreases."""
        node = Node(
            content="def calculate_total(items: list[Item], discount: float) -> Decimal:",
            type="function",
            name="calculate_total"
        )

        # Large budget: full signature
        full = strategy.render(node, budget=100)
        assert full == node.content

        # Medium budget: still full (fits)
        medium = strategy.render(node, budget=70)
        assert medium == node.content

        # Small budget: name only
        small = strategy.render(node, budget=20)
        assert small == "calculate_total"

        # Tiny budget: truncated name
        tiny = strategy.render(node, budget=8)
        assert tiny == "calcu..."

    def test_render_preserves_decorators_when_budget_allows(self, strategy):
        """Decorators included when budget sufficient."""
        node = Node(
            content="@property\ndef foo(self) -> int:",
            type="method",
            name="foo"
        )
        result = strategy.render(node, budget=50)
        assert result == "@property\ndef foo(self) -> int:"

        # But with tight budget, just name
        result_tight = strategy.render(node, budget=10)
        assert result_tight == "foo"
