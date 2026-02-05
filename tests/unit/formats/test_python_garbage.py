"""Tests for Python format garbage output prevention."""

import pytest
from nub.formats.python import PythonStrategy
from nub.core import compress_tree


class TestPythonGarbageOutput:
    """Test that tiny budgets produce clean fold markers, not garbage dots."""

    @pytest.fixture
    def strategy(self):
        return PythonStrategy()

    def test_class_with_many_methods_tight_budget(self, strategy):
        """A class with many methods should fold cleanly, not produce dots."""
        # Simulate a class with 50 methods
        methods = "\n".join([
            f"    def method_{i}(self):\n        pass" for i in range(50)
        ])
        code = f'''class BigClass:
    """A class with many methods."""
{methods}
'''
        root = strategy.parse(code)

        # Tiny budget that can't show all methods
        budget = 500
        lines = compress_tree(root, budget, strategy.rank, renderer=strategy.render)
        output = "\n".join(line.content for line in lines)

        # Should NOT contain single-char garbage lines
        garbage_lines = [l for l in lines if l.content.strip() == "."]
        assert len(garbage_lines) == 0, f"Found {len(garbage_lines)} garbage '.' lines"

        # With progressive LOD, should show names or fold markers (not truncated garbage)
        # Names like "method_0" or fold markers "[...N more...]"
        for line in lines:
            content = line.content.strip()
            # Skip class definition, fold markers, and budget truncation markers
            if content.startswith("class ") or content.startswith("[") or "truncated" in content:
                continue
            # Method names should not have truncation markers in the middle
            assert "..." not in content or content.endswith("..."), \
                f"Unexpected truncation: {content}"

    def test_no_garbage_dots_in_output(self, strategy):
        """Output should never contain single '.' lines."""
        code = '''
import os
import sys
from typing import List, Dict, Optional

class MyClass:
    """Docstring."""

    def method1(self): pass
    def method2(self): pass
    def method3(self): pass
    def method4(self): pass
    def method5(self): pass
    def method6(self): pass
    def method7(self): pass
    def method8(self): pass
    def method9(self): pass
    def method10(self): pass
'''
        root = strategy.parse(code)

        # Very tight budget
        budget = 200
        lines = compress_tree(root, budget, strategy.rank, renderer=strategy.render)

        # No line should be just "."
        for line in lines:
            stripped = line.content.strip()
            assert stripped != ".", f"Found garbage dot line: {repr(line.content)}"

    def test_minimum_useful_content(self, strategy):
        """Each rendered line should have meaningful content."""
        code = '''
class Example:
    def foo(self): pass
    def bar(self): pass
    def baz(self): pass
'''
        root = strategy.parse(code)

        budget = 100
        lines = compress_tree(root, budget, strategy.rank, renderer=strategy.render)

        for line in lines:
            stripped = line.content.strip()
            # Lines should either be:
            # - Fold markers [...]
            # - Truncation markers ...[
            # - Actual content (at least 5 chars of real content)
            if stripped and not stripped.startswith("[...") and not stripped.startswith("..."):
                # Real content line - should have meaningful length
                assert len(stripped) >= 3, f"Line too short to be useful: {repr(line.content)}"
