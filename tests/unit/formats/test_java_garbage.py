"""Tests for Java format garbage output prevention."""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_java")

from nub.core import compress_tree  # noqa: E402
from nub.formats.base import registry  # noqa: E402


@pytest.fixture
def strategy():
    s = registry.get_by_name("java")
    if s is None:
        pytest.skip("java strategy not registered")
    return s


class TestJavaGarbageOutput:
    def test_class_with_many_methods_tight_budget(self, strategy):
        methods = "\n".join(
            f"    public void method{i}() {{ }}" for i in range(50)
        )
        code = f"public class BigClass {{\n{methods}\n}}"
        root = strategy.parse(code)

        lines = compress_tree(root, 500, strategy.rank, renderer=strategy.render)

        garbage = [ln for ln in lines if ln.content.strip() == "."]
        assert len(garbage) == 0, f"Found {len(garbage)} garbage '.' lines"

    def test_no_garbage_dots(self, strategy):
        code = """public class MyClass {
    public void method1() {}
    public void method2() {}
    public void method3() {}
    public void method4() {}
    public void method5() {}
    public void method6() {}
    public void method7() {}
    public void method8() {}
    public void method9() {}
    public void method10() {}
}"""
        root = strategy.parse(code)
        lines = compress_tree(root, 200, strategy.rank, renderer=strategy.render)

        for ln in lines:
            assert ln.content.strip() != ".", f"Garbage dot: {repr(ln.content)}"

    def test_minimum_useful_content(self, strategy):
        code = """public class Example {
    public void foo() {}
    public void bar() {}
    public void baz() {}
}"""
        root = strategy.parse(code)
        lines = compress_tree(root, 100, strategy.rank, renderer=strategy.render)

        for ln in lines:
            stripped = ln.content.strip()
            if stripped and not stripped.startswith("[...") and not stripped.startswith("..."):
                assert len(stripped) >= 3, f"Too short: {repr(ln.content)}"
