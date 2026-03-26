"""Tests for Java progressive LOD rendering."""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_java")

from nub.dom import Node  # noqa: E402
from nub.formats.base import registry  # noqa: E402


@pytest.fixture
def strategy():
    s = registry.get_by_name("java")
    if s is None:
        pytest.skip("java strategy not registered")
    return s


class TestJavaProgressiveLOD:
    def test_full_content_when_budget_sufficient(self, strategy):
        node = Node(content="public void foo(int x)", type="method", name="foo")
        assert strategy.render(node, budget=100) == "public void foo(int x)"

    def test_name_only_when_tight(self, strategy):
        node = Node(
            content="public void foo(int x, String y, double z)",
            type="method", name="foo",
        )
        assert strategy.render(node, budget=10) == "foo"

    def test_none_when_zero(self, strategy):
        node = Node(content="public void foo()", type="method", name="foo")
        assert strategy.render(node, budget=0) is None

    def test_class_name_only(self, strategy):
        node = Node(
            content="public class MyVeryLongClassName extends Base implements Iface",
            type="class", name="MyVeryLongClassName",
        )
        result = strategy.render(node, budget=25)
        assert result == "MyVeryLongClassName"

    def test_progressive_degradation(self, strategy):
        node = Node(
            content="public List<Item> calculateTotal(List<Item> items, double discount)",
            type="method", name="calculateTotal",
        )
        full = strategy.render(node, budget=200)
        assert full == node.content

        small = strategy.render(node, budget=20)
        assert small == "calculateTotal"

        tiny = strategy.render(node, budget=8)
        assert tiny == "calcu..."

    def test_import_summary_truncated(self, strategy):
        node = Node(content="[58 imports, lines 12-200]", type="import_summary", name="imports")
        result = strategy.render(node, budget=15)
        assert result.endswith("...")
        assert len(result) <= 15

    def test_render_preserves_annotations(self, strategy):
        node = Node(
            content="@Override\npublic void foo()",
            type="method", name="foo",
        )
        assert strategy.render(node, budget=100) == "@Override\npublic void foo()"
        assert strategy.render(node, budget=10) == "foo"
