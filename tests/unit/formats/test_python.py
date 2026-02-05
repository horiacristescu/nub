"""
Unit tests for Python AST format strategy.
"""

import pytest

from nub.dom import Node
from nub.formats.python import PythonStrategy


@pytest.fixture
def strategy():
    return PythonStrategy()


class TestPythonStrategy:
    """Test PythonStrategy basics."""

    def test_name(self, strategy):
        assert strategy.name == "python"

    def test_extensions(self, strategy):
        assert ".py" in strategy.extensions

    def test_parse_empty(self, strategy):
        root = strategy.parse("")
        assert root.type == "module"
        assert len(root.children) == 0

    def test_parse_simple_function(self, strategy):
        code = '''def hello():
    """Say hello."""
    print("hello")
'''
        root = strategy.parse(code)
        assert root.type == "module"
        assert len(root.children) == 1

        func = root.children[0]
        assert func.type == "function"
        assert func.name == "hello"
        assert "def hello" in func.content

    def test_parse_function_with_args(self, strategy):
        code = '''def greet(name: str, count: int = 1) -> str:
    """Greet someone."""
    return f"Hello {name}" * count
'''
        root = strategy.parse(code)
        func = root.children[0]
        assert func.type == "function"
        assert "name: str" in func.content
        assert "count: int" in func.content
        assert "-> str" in func.content

    def test_parse_class(self, strategy):
        code = '''class Greeter:
    """A greeter class."""

    def greet(self, name: str) -> str:
        return f"Hello {name}"
'''
        root = strategy.parse(code)
        assert len(root.children) == 1

        cls = root.children[0]
        assert cls.type == "class"
        assert cls.name == "Greeter"
        # Class should have methods as children
        assert len(cls.children) >= 1
        assert cls.children[0].type == "method"
        assert cls.children[0].name == "greet"

    def test_parse_class_with_bases(self, strategy):
        code = '''class MyStrategy(FormatStrategy, ABC):
    """Custom strategy."""
    pass
'''
        root = strategy.parse(code)
        cls = root.children[0]
        assert "FormatStrategy" in cls.content
        assert "ABC" in cls.content

    def test_parse_imports(self, strategy):
        code = '''import os
from pathlib import Path
from typing import List, Dict
'''
        root = strategy.parse(code)
        # Imports should be collapsed into a summary
        summaries = [c for c in root.children if c.type == "import_summary"]
        assert len(summaries) == 1

        # Summary should mention count
        assert "3 imports" in summaries[0].content

    def test_parse_decorated_function(self, strategy):
        code = '''@property
def name(self) -> str:
    return "test"
'''
        root = strategy.parse(code)
        func = root.children[0]
        assert "@property" in func.content

    def test_parse_async_function(self, strategy):
        code = '''async def fetch(url: str) -> bytes:
    """Fetch URL."""
    pass
'''
        root = strategy.parse(code)
        func = root.children[0]
        assert "async def" in func.content

    def test_parse_skips_function_docstrings(self, strategy):
        """Function/method docstrings are skipped for compact overview."""
        code = '''def documented():
    """This is a docstring.

    With multiple lines.
    """
    pass
'''
        root = strategy.parse(code)
        func = root.children[0]
        # Docstrings are intentionally skipped for functions (compact overview)
        # Only class docstrings are preserved
        assert "def documented():" in func.content
        assert "docstring" not in func.content.lower()


class TestPythonRanking:
    """Test topology scoring for Python nodes."""

    def test_import_rank_medium(self, strategy):
        """Imports provide context but shouldn't dominate budget."""
        node = Node(content="import os", type="import")
        assert strategy.rank(node) >= 0.4
        assert strategy.rank(node) < 0.7  # Lower than classes/functions

    def test_class_rank_high(self, strategy):
        """Classes are primary content, should rank highest."""
        node = Node(content="class Foo:", type="class")
        assert strategy.rank(node) >= 0.8

    def test_function_rank_medium(self, strategy):
        node = Node(content="def bar():", type="function")
        assert strategy.rank(node) >= 0.7

    def test_method_rank_medium(self, strategy):
        node = Node(content="def bar(self):", type="method")
        assert strategy.rank(node) >= 0.5

    def test_body_rank_lower(self, strategy):
        node = Node(content="x = 1", type="body")
        assert strategy.rank(node) <= 0.5


class TestPythonSyntaxErrors:
    """Test handling of syntax errors."""

    def test_syntax_error_graceful(self, strategy):
        """Syntax errors should fall back gracefully."""
        code = "def broken(:\n    pass"
        # Should not raise, should return something usable
        root = strategy.parse(code)
        assert root is not None
        # Should fall back to treating as text
        assert root.type in ("module", "document", "text")


class TestPythonComplexCode:
    """Test with realistic Python code."""

    def test_parse_realistic_module(self, strategy):
        code = '''"""Module docstring."""

import json
from pathlib import Path

from .base import Node


class Parser:
    """Parse stuff."""

    def __init__(self, config: dict):
        self.config = config

    def parse(self, content: str) -> Node:
        """Parse content into tree."""
        return Node(content=content, type="text")


def main():
    """Entry point."""
    p = Parser({})
    print(p.parse("hello"))
'''
        root = strategy.parse(code)

        # Should have import summary, class, and function
        types = [c.type for c in root.children]
        assert "import_summary" in types
        assert "class" in types
        assert "function" in types

        # Find the class
        parser_class = next(c for c in root.children if c.type == "class")
        assert parser_class.name == "Parser"

        # Class should have methods
        method_names = [m.name for m in parser_class.children if m.type == "method"]
        assert "__init__" in method_names
        assert "parse" in method_names


class TestPythonRegistry:
    """Test that Python strategy is registered."""

    def test_python_registered(self):
        from nub.formats.base import registry
        strategy = registry.get_by_extension(".py")
        assert strategy is not None
        assert strategy.name == "python"

    def test_py_extension_works(self):
        from nub.formats.base import registry
        strategy = registry.get_by_extension("py")  # Without dot
        assert strategy is not None
        assert strategy.name == "python"
