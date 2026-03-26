"""
Tree-sitter format strategy — generic AST support for multiple languages.

Uses tree-sitter's uniform CST API with heuristic node classification
to support any language without per-language mapping config. Adding a
new language requires only a LANGUAGES entry.

Optional dependency: install via `pip install nub[tree-sitter]`.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any

from ..dom import Node
from .base import FormatStrategy, registry


@dataclass(frozen=True)
class LangDef:
    """Minimal per-language definition — everything else is auto-detected."""
    extensions: tuple[str, ...]
    package: str
    language_func: str = "language"


LANGUAGES: dict[str, LangDef] = {
    "c":          LangDef((".c", ".h"),                           "tree_sitter_c"),
    "cpp":        LangDef((".cpp", ".hpp", ".cc", ".cxx", ".hh"), "tree_sitter_cpp"),
    "csharp":     LangDef((".cs",),                               "tree_sitter_c_sharp"),
    "go":         LangDef((".go",),                               "tree_sitter_go"),
    "java":       LangDef((".java",),                             "tree_sitter_java"),
    "javascript": LangDef((".js", ".jsx", ".mjs", ".cjs"),       "tree_sitter_javascript"),
    "kotlin":     LangDef((".kt", ".kts"),                        "tree_sitter_kotlin"),
    "php":        LangDef((".php",),                              "tree_sitter_php", "language_php"),
    "ruby":       LangDef((".rb",),                               "tree_sitter_ruby"),
    "rust":       LangDef((".rs",),                               "tree_sitter_rust"),
    "sql":        LangDef((".sql",),                              "tree_sitter_sql"),
    "swift":      LangDef((".swift",),                            "tree_sitter_swift"),
    "typescript": LangDef((".ts", ".tsx"),                        "tree_sitter_typescript",
                          "language_typescript"),
}

_RANK_SCORES: dict[str, float] = {
    "class": 0.9,
    "function": 0.8,
    "constructor": 0.75,
    "method": 0.7,
    "constant": 0.6,
    "field": 0.55,
    "package": 0.5,
    "import_summary": 0.4,
    "text": 0.3,
}

# Node types that are structural containers with child members
_CONTAINER_TYPES = frozenset({"class", "package"})

# Node types eligible for name-only LOD rendering
_NAMED_LOD_TYPES = frozenset({
    "class", "function", "method", "constructor",
    "constant", "field",
})

# Keywords that indicate type-container declarations
_TYPE_KEYWORDS = ("class", "struct", "interface", "enum", "trait", "impl", "record")


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------

def _classify(ts_node: Any) -> str | None:
    """Classify a tree-sitter node into a nub node type.

    Uses keyword heuristics on the node's ``type`` string combined with
    structural probing via ``child_by_field_name``.

    Safety: this is only called on direct children of the root node or of
    a body node — i.e. declaration-level nodes, never expression-level.
    This is why substring matching on the type name is safe: at these
    tree positions, ``method_declaration`` appears but ``method_invocation``
    does not.
    """
    t = ts_node.type

    # Import-like — match "use" as a snake_case word, not as a substring of
    # "clause"/"cause"/etc.  Covers: use_declaration, namespace_use_declaration.
    if (
        "import" in t
        or "using" in t
        or t.startswith("use_") or "_use_" in t
        or t == "preproc_include"
    ):
        return "import"

    # Package/namespace
    if "package" in t or "namespace" in t:
        return "package"

    # Callables — check "constructor" before type keywords because
    # "struct" is a substring of "constructor"
    if "constructor" in t:
        return "constructor"
    if "method" in t:
        return "method"
    if "function" in t:
        return "function"

    # Type containers
    if any(kw in t for kw in _TYPE_KEYWORDS):
        return "class"

    # Fields / properties
    if "field" in t or "property" in t:
        return "field"

    # Fallback: probe tree-sitter fields to detect unnamed patterns
    if ts_node.child_by_field_name("name"):
        if ts_node.child_by_field_name("body"):
            return "class"
        if ts_node.child_by_field_name("parameters"):
            return "function"
        # Check children for type-container types (Go: type_spec → struct_type)
        for sub in ts_node.children:
            if sub.is_named and any(kw in sub.type for kw in _TYPE_KEYWORDS):
                return "class"

    return None


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------

def _extract_name(ts_node: Any, source: bytes) -> str | None:
    """Extract declaration name, with declarator fallback for C-family."""
    name_node = ts_node.child_by_field_name("name")
    if name_node:
        return source[name_node.start_byte:name_node.end_byte].decode("utf-8")

    # C/C++ fallback: drill through nested declarators
    decl = ts_node.child_by_field_name("declarator")
    if decl:
        while decl.child_by_field_name("declarator"):
            decl = decl.child_by_field_name("declarator")
        inner = decl.child_by_field_name("name") or decl
        return source[inner.start_byte:inner.end_byte].decode("utf-8")

    return None


def _find_body(ts_node: Any) -> Any | None:
    """Find the body child — by named field first, then by suffix heuristic.

    Suffixes are intentionally narrow: ``_body`` and ``block`` are unambiguous
    container types.  Broader suffixes like ``_list`` are avoided because they
    would match ``parameter_list``, ``argument_list``, etc.
    """
    body = ts_node.child_by_field_name("body")
    if body is not None:
        return body
    # Fallback: some grammars (Kotlin, etc.) don't expose body as a named field.
    for child in reversed(ts_node.children):
        if child.is_named and child.type.endswith(("_body", "block")):
            return child
    return None


def _extract_signature(ts_node: Any, source: bytes) -> str:
    """Extract declaration signature — everything before the body block."""
    body = _find_body(ts_node)
    if body:
        sig = source[ts_node.start_byte:body.start_byte].decode("utf-8").rstrip()
        if sig.endswith("{"):
            sig = sig[:-1].rstrip()
        return sig
    return source[ts_node.start_byte:ts_node.end_byte].decode("utf-8")


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------

class TreeSitterStrategy(FormatStrategy):
    """Generic tree-sitter strategy parameterized by language."""

    def __init__(self, lang_name: str, extensions: tuple[str, ...], ts_language: Any):
        self._lang_name = lang_name
        self._extensions = list(extensions)
        from tree_sitter import Language, Parser  # type: ignore[import-not-found]
        self._parser = Parser(Language(ts_language))

    @property
    def name(self) -> str:
        return self._lang_name

    @property
    def extensions(self) -> list[str]:
        return self._extensions

    def parse(self, content: str) -> Node:
        root = Node(content="", type="module", name="module")

        if not content.strip():
            return root

        source = content.encode("utf-8")
        try:
            tree = self._parser.parse(source)
        except Exception:
            root.add_child(Node(content=content, type="text", name="unparseable"))
            return root

        import_count = 0
        first_import_line: int | None = None
        last_import_line: int | None = None

        for child in tree.root_node.children:
            if not child.is_named:
                continue

            nub_type = _classify(child)

            if nub_type == "import":
                import_count += 1
                if first_import_line is None:
                    first_import_line = child.start_point[0] + 1
                last_import_line = child.end_point[0] + 1
                continue

            if nub_type is None:
                # Unwrap transparent wrappers (e.g., Go type_declaration → type_spec)
                for sub in child.children:
                    if sub.is_named:
                        sub_type = _classify(sub)
                        if sub_type and sub_type != "import":
                            self._add_node(sub, sub_type, source, root)
                continue

            self._add_node(child, nub_type, source, root)

        if import_count > 0:
            if first_import_line and last_import_line:
                summary = f"[{import_count} imports, lines {first_import_line}-{last_import_line}]"
            else:
                summary = f"[{import_count} imports]"
            root.children.insert(
                0, Node(content=summary, type="import_summary", name="imports")
            )

        if not root.children:
            root.add_child(Node(content=content, type="text", name="unparseable"))

        return root

    def _add_node(self, ts_node: Any, nub_type: str, source: bytes, parent: Node) -> None:
        """Create a nub Node from a tree-sitter node and add it to parent."""
        name = _extract_name(ts_node, source)
        sig = _extract_signature(ts_node, source)
        node = Node(
            content=sig, type=nub_type, name=name,
            source_line=ts_node.start_point[0] + 1,
        )
        if nub_type in _CONTAINER_TYPES:
            self._parse_body(ts_node, source, node)
        parent.add_child(node)

    def _parse_body(self, ts_node: Any, source: bytes, parent: Node) -> None:
        """Recurse into a container's body for methods, fields, inner types."""
        body = _find_body(ts_node)
        if not body:
            return
        for child in body.children:
            if not child.is_named:
                continue
            nub_type = _classify(child)
            if nub_type is None:
                continue
            self._add_node(child, nub_type, source, parent)

    def rank(self, node: Node) -> float:
        return _RANK_SCORES.get(node.type, 0.5)

    def render(self, node: Node, budget: int) -> str | None:
        if budget <= 0:
            return None

        content = node.content
        name = node.name

        # Full content fits
        if len(content) <= budget:
            return content

        # Named structural nodes: try name-only
        if name and node.type in _NAMED_LOD_TYPES:
            if len(name) <= budget:
                return name
            if budget >= 4:
                return name[:budget - 3] + "..."

        # Import/package summary: truncate
        if node.type in ("import_summary", "package") and budget >= 10:
            return content[:budget - 3] + "..."

        # Fallback: truncate content
        if budget >= 10:
            return content[:budget - 3] + "..."

        return None


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_registered_names: frozenset[str] = frozenset()
_registered_exts: frozenset[str] = frozenset()


def _register_available() -> None:
    """Register tree-sitter strategies for all installed language grammars."""
    global _registered_names, _registered_exts

    try:
        import tree_sitter  # type: ignore[import-not-found]  # noqa: F401
    except ImportError:
        return

    names: set[str] = set()
    exts: set[str] = set()
    for lang_name, lang_def in LANGUAGES.items():
        try:
            mod = importlib.import_module(lang_def.package)
            lang = getattr(mod, lang_def.language_func)()
            strategy = TreeSitterStrategy(lang_name, lang_def.extensions, lang)
            registry.register(strategy)
            names.add(lang_name)
            for ext in lang_def.extensions:
                exts.add(ext.lstrip("."))
        except (ImportError, AttributeError):
            pass
    _registered_names = frozenset(names)
    _registered_exts = frozenset(exts)


_register_available()


def is_registered(name_or_ext: str) -> bool:
    """Check if a language name or file extension was actually registered.

    Returns False if tree-sitter is not installed or the specific grammar
    package is missing — even if the language appears in LANGUAGES.
    """
    return name_or_ext in _registered_names or name_or_ext in _registered_exts
