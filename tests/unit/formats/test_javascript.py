"""Smoke tests for JavaScript parsing via tree-sitter strategy."""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_javascript")

from nub.formats.base import registry  # noqa: E402


@pytest.fixture
def strategy():
    s = registry.get_by_name("javascript")
    if s is None:
        pytest.skip("javascript strategy not registered")
    return s


class TestJavaScriptParsing:
    def test_parse_class(self, strategy):
        code = """class UserService {
    constructor(db) {
        this.db = db;
    }
    async getUser(id) {
        return this.db.find(id);
    }
}"""
        root = strategy.parse(code)
        classes = [c for c in root.children if c.type == "class"]
        assert len(classes) == 1
        assert classes[0].name == "UserService"

    def test_parse_function(self, strategy):
        code = """function greet(name) {
    return `Hello ${name}`;
}"""
        root = strategy.parse(code)
        funcs = [c for c in root.children if c.type == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "greet"

    def test_parse_imports_collapsed(self, strategy):
        code = """import { useState } from 'react';
import axios from 'axios';
import './styles.css';

function App() { return null; }"""
        root = strategy.parse(code)
        summaries = [c for c in root.children if c.type == "import_summary"]
        assert len(summaries) == 1
        assert "3 imports" in summaries[0].content

    def test_parse_class_methods(self, strategy):
        code = """class Calc {
    add(a, b) { return a + b; }
    subtract(a, b) { return a - b; }
}"""
        root = strategy.parse(code)
        cls = [c for c in root.children if c.type == "class"][0]
        methods = [c for c in cls.children if c.type == "method"]
        assert len(methods) == 2

    def test_registry(self):
        assert registry.get_by_extension(".js") is not None
        assert registry.get_by_extension(".js").name == "javascript"
        assert registry.get_by_extension(".jsx") is not None
