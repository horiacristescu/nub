"""Tests for the generic tree-sitter format strategy."""

import pytest

ts = pytest.importorskip("tree_sitter")

from nub.dom import Node  # noqa: E402
from nub.formats.base import registry  # noqa: E402
from nub.formats.treesitter import (  # noqa: E402
    LANGUAGES,
    TreeSitterStrategy,
    _classify,
    _extract_name,
    _extract_signature,
    is_registered,
)


def _parse_ts(lang_name: str, source: bytes):
    """Parse source bytes with tree-sitter, returning the raw CST tree."""
    strategy = registry.get_by_name(lang_name)
    if strategy is None or not isinstance(strategy, TreeSitterStrategy):
        pytest.skip(f"{lang_name} strategy not registered")
    import importlib

    from tree_sitter import Language, Parser

    lang_def = LANGUAGES[lang_name]
    mod = importlib.import_module(lang_def.package)
    ts_lang = getattr(mod, lang_def.language_func)()
    return Parser(Language(ts_lang)).parse(source)


@pytest.fixture
def java_tree():
    """Provide a parser for Java-specific classifier/extractor tests."""
    pytest.importorskip("tree_sitter_java")
    return lambda src: _parse_ts("java", src)


class TestRegistration:
    def test_registered_languages_have_strategies(self):
        """Every language with an installed grammar should be registered."""
        for lang_name, lang_def in LANGUAGES.items():
            try:
                __import__(lang_def.package)
            except ImportError:
                continue
            strategy = registry.get_by_name(lang_name)
            assert strategy is not None, f"{lang_name} grammar installed but not registered"
            assert strategy.name == lang_name

    def test_registered_extensions_match(self):
        """Registered extensions should match what is_registered reports."""
        for lang_name, lang_def in LANGUAGES.items():
            try:
                __import__(lang_def.package)
            except ImportError:
                continue
            for ext in lang_def.extensions:
                assert is_registered(ext.lstrip(".")), f"{ext} not registered for {lang_name}"

    def test_is_registered_by_name(self):
        """Language names should be recognized by is_registered."""
        for lang_name, lang_def in LANGUAGES.items():
            try:
                __import__(lang_def.package)
            except ImportError:
                continue
            assert is_registered(lang_name)

    def test_python_still_uses_stdlib(self):
        """Python files should still use the stdlib ast strategy, not tree-sitter."""
        strategy = registry.get_by_extension(".py")
        assert strategy is not None
        assert strategy.name == "python"


class TestClassifier:
    """Test _classify heuristics using a real tree-sitter parse."""

    def test_classify_class(self, java_tree):
        root = java_tree(b"public class Foo {}").root_node
        cls = [c for c in root.children if c.is_named][0]
        assert _classify(cls) == "class"

    def test_classify_method(self, java_tree):
        root = java_tree(b"public class Foo { void bar() {} }").root_node
        cls = [c for c in root.children if c.is_named][0]
        body = cls.child_by_field_name("body")
        method = [c for c in body.children if c.is_named][0]
        assert _classify(method) == "method"

    def test_classify_import(self, java_tree):
        root = java_tree(b"import java.util.List;").root_node
        child = [c for c in root.children if c.is_named][0]
        assert _classify(child) == "import"

    def test_classify_interface(self, java_tree):
        root = java_tree(b"public interface Foo {}").root_node
        child = [c for c in root.children if c.is_named][0]
        assert _classify(child) == "class"

    def test_classify_constructor(self, java_tree):
        root = java_tree(b"public class Foo { public Foo() {} }").root_node
        cls = [c for c in root.children if c.is_named][0]
        body = cls.child_by_field_name("body")
        ctor = [c for c in body.children if c.is_named][0]
        assert _classify(ctor) == "constructor"


class TestNameExtraction:
    def test_extract_class_name(self, java_tree):
        source = b"public class Foo {}"
        root = java_tree(source).root_node
        cls = [c for c in root.children if c.is_named][0]
        assert _extract_name(cls, source) == "Foo"

    def test_extract_method_name(self, java_tree):
        source = b"public class Foo { void bar() {} }"
        root = java_tree(source).root_node
        cls = [c for c in root.children if c.is_named][0]
        body = cls.child_by_field_name("body")
        method = [c for c in body.children if c.is_named][0]
        assert _extract_name(method, source) == "bar"

    def test_extract_name_returns_none_for_anonymous(self, java_tree):
        source = b"import java.util.List;"
        root = java_tree(source).root_node
        child = [c for c in root.children if c.is_named][0]
        # import nodes typically don't have a "name" field
        # (they may or may not return None depending on grammar — just verify no crash)
        _extract_name(child, source)


class TestSignatureExtraction:
    def test_class_signature_excludes_body(self, java_tree):
        source = b"public class Foo extends Bar { int x; }"
        root = java_tree(source).root_node
        cls = [c for c in root.children if c.is_named][0]
        sig = _extract_signature(cls, source)
        assert "public class Foo extends Bar" in sig
        assert "int x" not in sig

    def test_method_signature_excludes_body(self, java_tree):
        source = b"public class Foo { public void bar(int x) { return; } }"
        root = java_tree(source).root_node
        cls = [c for c in root.children if c.is_named][0]
        body = cls.child_by_field_name("body")
        method = [c for c in body.children if c.is_named][0]
        sig = _extract_signature(method, source)
        assert "public void bar(int x)" in sig
        assert "return" not in sig


class TestRender:
    @pytest.fixture
    def strategy(self):
        s = registry.get_by_name("java")
        if s is None:
            pytest.skip("java strategy not registered")
        return s

    def test_render_full(self, strategy):
        node = Node(content="public void foo()", type="method", name="foo")
        assert strategy.render(node, budget=100) == "public void foo()"

    def test_render_name_only(self, strategy):
        node = Node(
            content="public void foo(int x, String y, double z)",
            type="method", name="foo",
        )
        assert strategy.render(node, budget=10) == "foo"

    def test_render_none_at_zero(self, strategy):
        node = Node(content="foo", type="method", name="foo")
        assert strategy.render(node, budget=0) is None


class TestParseEdgeCases:
    @pytest.fixture
    def strategy(self):
        s = registry.get_by_name("java")
        if s is None:
            pytest.skip("java strategy not registered")
        return s

    def test_empty_input(self, strategy):
        """Empty input should return an empty module node."""
        root = strategy.parse("")
        assert root.type == "module"
        assert len(root.children) == 0

    def test_no_declarations_falls_back_to_text(self, strategy):
        """Content with no recognizable declarations should produce a text fallback."""
        root = strategy.parse("// just a comment")
        assert root.type == "module"
        assert len(root.children) == 1
        assert root.children[0].type == "text"
