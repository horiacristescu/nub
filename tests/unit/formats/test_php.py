"""Smoke tests for PHP parsing via tree-sitter strategy."""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_php")

from nub.formats.base import registry  # noqa: E402


@pytest.fixture
def strategy():
    s = registry.get_by_name("php")
    if s is None:
        pytest.skip("php strategy not registered")
    return s


class TestPhpParsing:
    def test_parse_class(self, strategy):
        code = """<?php
class UserController {
    public function index() {
        return view('users.index');
    }
}"""
        root = strategy.parse(code)
        classes = [c for c in root.children if c.type == "class"]
        assert len(classes) == 1
        assert classes[0].name == "UserController"

    def test_parse_methods(self, strategy):
        code = """<?php
class Foo {
    public function bar(): string {
        return "bar";
    }
    private function baz(int $x): void {}
}"""
        root = strategy.parse(code)
        cls = [c for c in root.children if c.type == "class"][0]
        methods = [c for c in cls.children if c.type == "method"]
        assert len(methods) == 2
        names = {m.name for m in methods}
        assert "bar" in names
        assert "baz" in names

    def test_parse_interface(self, strategy):
        code = """<?php
interface Renderable {
    public function render(): string;
}"""
        root = strategy.parse(code)
        ifaces = [c for c in root.children if c.type == "class"]
        assert len(ifaces) == 1
        assert ifaces[0].name == "Renderable"

    def test_parse_trait(self, strategy):
        code = """<?php
trait HasTimestamps {
    public function getCreatedAt(): DateTime {
        return $this->createdAt;
    }
}"""
        root = strategy.parse(code)
        traits = [c for c in root.children if c.type == "class"]
        assert len(traits) == 1
        assert traits[0].name == "HasTimestamps"

    def test_parse_function(self, strategy):
        code = """<?php
function helper(string $input): string {
    return strtoupper($input);
}"""
        root = strategy.parse(code)
        funcs = [c for c in root.children if c.type == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "helper"

    def test_parse_namespace(self, strategy):
        code = """<?php
namespace App\\Http\\Controllers;

class HomeController {}"""
        root = strategy.parse(code)
        pkgs = [c for c in root.children if c.type == "package"]
        assert len(pkgs) == 1

    def test_parse_use_as_import(self, strategy):
        code = """<?php
use App\\Models\\User;
use Illuminate\\Http\\Request;

class Controller {}"""
        root = strategy.parse(code)
        summaries = [c for c in root.children if c.type == "import_summary"]
        assert len(summaries) == 1
        assert "2 imports" in summaries[0].content

    def test_registry(self):
        assert registry.get_by_extension(".php") is not None
        assert registry.get_by_extension(".php").name == "php"
