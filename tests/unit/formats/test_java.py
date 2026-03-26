"""Tests for Java parsing via tree-sitter strategy."""

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


class TestJavaParsing:
    def test_parse_empty(self, strategy):
        root = strategy.parse("")
        assert root.type == "module"
        assert len(root.children) == 0

    def test_parse_simple_class(self, strategy):
        code = "public class Foo {}"
        root = strategy.parse(code)
        assert len(root.children) == 1
        cls = root.children[0]
        assert cls.type == "class"
        assert cls.name == "Foo"

    def test_parse_class_with_methods(self, strategy):
        code = """public class Greeter {
    public String greet(String name) {
        return "Hello " + name;
    }

    public void farewell() {
        System.out.println("Bye");
    }
}"""
        root = strategy.parse(code)
        cls = root.children[0]
        assert cls.type == "class"
        assert cls.name == "Greeter"
        methods = [c for c in cls.children if c.type == "method"]
        assert len(methods) == 2
        names = {m.name for m in methods}
        assert "greet" in names
        assert "farewell" in names

    def test_parse_interface(self, strategy):
        code = """public interface Comparable<T> {
    int compareTo(T other);
}"""
        root = strategy.parse(code)
        iface = root.children[0]
        assert iface.type == "class"
        assert iface.name == "Comparable"

    def test_parse_enum(self, strategy):
        code = """public enum Color {
    RED, GREEN, BLUE;
}"""
        root = strategy.parse(code)
        enum = root.children[0]
        assert enum.type == "class"
        assert enum.name == "Color"

    def test_parse_imports_collapsed(self, strategy):
        code = """import java.util.List;
import java.util.Map;
import java.io.IOException;

public class Foo {}"""
        root = strategy.parse(code)
        summaries = [c for c in root.children if c.type == "import_summary"]
        assert len(summaries) == 1
        assert "3 imports" in summaries[0].content

    def test_parse_constructor(self, strategy):
        code = """public class Foo {
    private int x;
    public Foo(int x) {
        this.x = x;
    }
}"""
        root = strategy.parse(code)
        cls = root.children[0]
        constructors = [c for c in cls.children if c.type == "constructor"]
        assert len(constructors) >= 1

    def test_parse_nested_class(self, strategy):
        code = """public class Outer {
    private static class Inner {
        void method() {}
    }
}"""
        root = strategy.parse(code)
        outer = root.children[0]
        assert outer.name == "Outer"
        inners = [c for c in outer.children if c.type == "class"]
        assert len(inners) == 1
        assert inners[0].name == "Inner"

    def test_parse_annotations(self, strategy):
        code = """public class Foo {
    @Override
    public String toString() {
        return "Foo";
    }
}"""
        root = strategy.parse(code)
        cls = root.children[0]
        methods = [c for c in cls.children if c.type == "method"]
        assert len(methods) >= 1
        assert "@Override" in methods[0].content

    def test_parse_generics(self, strategy):
        code = """public class Container<T extends Comparable<T>> {
    private T value;
    public T getValue() { return value; }
}"""
        root = strategy.parse(code)
        cls = root.children[0]
        assert cls.name == "Container"
        assert "<T" in cls.content

    def test_signature_excludes_body(self, strategy):
        code = """public class Foo {
    public int compute(int a, int b) {
        int result = a + b;
        return result;
    }
}"""
        root = strategy.parse(code)
        cls = root.children[0]
        methods = [c for c in cls.children if c.type == "method"]
        assert len(methods) == 1
        assert "compute" in methods[0].content
        assert "result" not in methods[0].content

    def test_parse_package(self, strategy):
        code = """package com.example.app;

public class App {}"""
        root = strategy.parse(code)
        pkgs = [c for c in root.children if c.type == "package"]
        assert len(pkgs) == 1


class TestJavaRanking:
    def test_class_highest(self, strategy):
        assert strategy.rank(Node(content="", type="class")) >= 0.8

    def test_method_medium(self, strategy):
        assert strategy.rank(Node(content="", type="method")) >= 0.5

    def test_field_lower(self, strategy):
        assert strategy.rank(Node(content="", type="field")) < 0.7

    def test_import_summary_low(self, strategy):
        assert strategy.rank(Node(content="", type="import_summary")) <= 0.5


class TestJavaRegistry:
    def test_java_by_extension(self):
        assert registry.get_by_extension(".java") is not None
        assert registry.get_by_extension(".java").name == "java"

    def test_java_by_name(self):
        assert registry.get_by_name("java") is not None
