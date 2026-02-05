"""
Tier 0: Data Model Contract Tests

These tests define the core DOM structure before any strategy code.
They pin down the contract that all strategies must honor.
"""

import pytest
from nub.dom import Node, Link, find_named, collect_named


class TestNodeCreation:
    def test_node_creation_with_content(self):
        node = Node(content="hello world")
        assert node.content == "hello world"

    def test_node_creation_with_type(self):
        node = Node(content="x", type="function")
        assert node.type == "function"

    def test_node_default_type_is_text(self):
        node = Node(content="x")
        assert node.type == "text"

    def test_node_creation_with_name(self):
        node = Node(content="def foo():", name="foo")
        assert node.name == "foo"
        assert node.is_named

    def test_node_without_name_is_anonymous(self):
        node = Node(content="just some text")
        assert node.name is None
        assert not node.is_named

    def test_node_creation_with_children(self):
        child1 = Node(content="child1")
        child2 = Node(content="child2")
        parent = Node(content="parent", children=[child1, child2])
        assert len(parent.children) == 2
        assert parent.children[0] is child1
        assert parent.children[1] is child2

    def test_node_add_child(self):
        parent = Node(content="parent")
        child = Node(content="child")
        result = parent.add_child(child)
        assert result is child
        assert child in parent.children


class TestNodeNaming:
    def test_named_node_can_be_link_target(self):
        source = Node(content="a", name="source")
        target = Node(content="b", name="target")
        link = Link(source=source, target=target)
        assert link.source is source
        assert link.target is target

    def test_anonymous_node_cannot_be_link_target(self):
        source = Node(content="a", name="source")
        target = Node(content="b")  # anonymous
        with pytest.raises(ValueError, match="target must be named"):
            Link(source=source, target=target)

    def test_anonymous_node_cannot_be_link_source(self):
        source = Node(content="a")  # anonymous
        target = Node(content="b", name="target")
        with pytest.raises(ValueError, match="source must be named"):
            Link(source=source, target=target)


class TestLinkCreation:
    def test_link_creation_between_named_nodes(self):
        node_a = Node(content="module A", name="mod_a")
        node_b = Node(content="module B", name="mod_b")
        link = Link(source=node_a, target=node_b)
        assert link.source.name == "mod_a"
        assert link.target.name == "mod_b"

    def test_link_is_directional(self):
        a = Node(content="a", name="a")
        b = Node(content="b", name="b")
        link_ab = Link(source=a, target=b)
        link_ba = Link(source=b, target=a)
        assert link_ab.source is a and link_ab.target is b
        assert link_ba.source is b and link_ba.target is a


class TestTreeTraversal:
    def test_tree_traversal_depth_first(self):
        root = Node(content="root", name="root")
        child1 = Node(content="c1", name="c1")
        child2 = Node(content="c2", name="c2")
        grandchild = Node(content="gc", name="gc")
        root.children = [child1, child2]
        child1.children = [grandchild]

        names = [n.name for n in root.depth_first()]
        assert names == ["root", "c1", "gc", "c2"]

    def test_tree_traversal_breadth_first(self):
        root = Node(content="root", name="root")
        child1 = Node(content="c1", name="c1")
        child2 = Node(content="c2", name="c2")
        grandchild = Node(content="gc", name="gc")
        root.children = [child1, child2]
        child1.children = [grandchild]

        names = [n.name for n in root.breadth_first()]
        assert names == ["root", "c1", "c2", "gc"]

    def test_single_node_traversal(self):
        node = Node(content="alone", name="alone")
        assert list(node.depth_first()) == [node]
        assert list(node.breadth_first()) == [node]


class TestTreeUtilities:
    def test_find_named_exists(self):
        root = Node(content="root", name="root")
        target = Node(content="target", name="target")
        root.add_child(Node(content="other")).add_child(target)

        found = find_named(root, "target")
        assert found is target

    def test_find_named_not_exists(self):
        root = Node(content="root", name="root")
        found = find_named(root, "nonexistent")
        assert found is None

    def test_collect_named(self):
        root = Node(content="root", name="root")
        named_child = Node(content="named", name="named")
        anon_child = Node(content="anon")
        root.children = [named_child, anon_child]

        named_nodes = collect_named(root)
        assert "root" in named_nodes
        assert "named" in named_nodes
        assert len(named_nodes) == 2
