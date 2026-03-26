"""Smoke tests for Go parsing via tree-sitter strategy.

Go is tested explicitly because it exercises the type_declaration → type_spec
unwrapping path that other languages don't need.
"""

import pytest

pytest.importorskip("tree_sitter")
pytest.importorskip("tree_sitter_go")

from nub.formats.base import registry  # noqa: E402


@pytest.fixture
def strategy():
    s = registry.get_by_name("go")
    if s is None:
        pytest.skip("go strategy not registered")
    return s


class TestGoParsing:
    def test_parse_struct(self, strategy):
        """Go structs are wrapped in type_declaration → type_spec; verify unwrapping."""
        code = """package main

type Server struct {
    addr string
    port int
}"""
        root = strategy.parse(code)
        structs = [c for c in root.children if c.type == "class"]
        assert len(structs) == 1
        assert structs[0].name == "Server"

    def test_parse_interface(self, strategy):
        code = """package main

type Reader interface {
    Read(p []byte) (n int, err error)
}"""
        root = strategy.parse(code)
        ifaces = [c for c in root.children if c.type == "class"]
        assert len(ifaces) == 1
        assert ifaces[0].name == "Reader"

    def test_parse_function(self, strategy):
        code = """package main

func NewServer(addr string, port int) *Server {
    return &Server{addr: addr, port: port}
}"""
        root = strategy.parse(code)
        funcs = [c for c in root.children if c.type == "function"]
        assert len(funcs) == 1
        assert funcs[0].name == "NewServer"
        assert "return" not in funcs[0].content

    def test_parse_method(self, strategy):
        code = """package main

func (s *Server) Start() error {
    return nil
}"""
        root = strategy.parse(code)
        methods = [c for c in root.children if c.type == "method"]
        assert len(methods) == 1
        assert methods[0].name == "Start"

    def test_parse_imports_collapsed(self, strategy):
        code = """package main

import (
    "fmt"
    "net/http"
)

func main() {}"""
        root = strategy.parse(code)
        summaries = [c for c in root.children if c.type == "import_summary"]
        assert len(summaries) == 1

    def test_parse_package(self, strategy):
        code = """package main

func main() {}"""
        root = strategy.parse(code)
        pkgs = [c for c in root.children if c.type == "package"]
        assert len(pkgs) == 1

    def test_registry(self):
        assert registry.get_by_extension(".go") is not None
        assert registry.get_by_extension(".go").name == "go"
