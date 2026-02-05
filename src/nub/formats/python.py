"""
Python AST format strategy.

Parses Python using stdlib ast module. Chunks by module structure:
imports (collapsed), classes, functions. Preserves signatures, docstrings, decorators.

Imports are collapsed into a single summary like "[58 imports, lines 1-200]"
to prevent them from dominating budget allocation.

Topology scores prioritize code structure over import details:
- classes: primary content (highest)
- functions: callable units (high)
- methods: within class context (medium)
- imports: collapsed summary (low)
- body: implementation details (lowest)
"""

from __future__ import annotations

import ast

from ..dom import Node
from .base import FormatStrategy, registry


class PythonStrategy(FormatStrategy):
    """Python AST parser strategy with semantic structure."""

    @property
    def name(self) -> str:
        return "python"

    @property
    def extensions(self) -> list[str]:
        return [".py", ".pyw"]

    def parse(self, content: str) -> Node:
        """Parse Python AST into tree of nodes."""
        root = Node(content="", type="module", name="module")

        if not content.strip():
            return root

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # Fall back to text-like treatment on syntax error
            root.type = "module"
            root.add_child(Node(content=content, type="text", name="unparseable"))
            return root

        # Get source lines for extracting original text
        lines = content.splitlines()

        # Collect imports separately to summarize them
        import_count = 0
        first_import_line = None
        last_import_line = None

        # Process top-level nodes
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                import_count += 1
                if first_import_line is None:
                    first_import_line = node.lineno
                last_import_line = getattr(node, "end_lineno", node.lineno)
            else:
                child = self._convert_node(node, lines)
                if child:
                    root.add_child(child)

        # Add import summary as first child if there were imports
        if import_count > 0:
            if first_import_line and last_import_line:
                summary = f"[{import_count} imports, lines {first_import_line}-{last_import_line}]"
            else:
                summary = f"[{import_count} imports]"
            import_node = Node(content=summary, type="import_summary", name="imports")
            # Insert at beginning
            root.children.insert(0, import_node)

        return root

    def _convert_node(
        self, node: ast.AST, lines: list[str], is_method: bool = False
    ) -> Node | None:
        """Convert an AST node to our Node format."""
        if isinstance(node, ast.Import):
            return self._convert_import(node, lines)
        elif isinstance(node, ast.ImportFrom):
            return self._convert_import_from(node, lines)
        elif isinstance(node, ast.ClassDef):
            return self._convert_class(node, lines)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return self._convert_function(node, lines, is_method=is_method)
        elif isinstance(node, ast.Assign):
            return self._convert_assign(node, lines)
        elif isinstance(node, ast.AnnAssign):
            return self._convert_annassign(node, lines)
        # Skip other node types (expressions, etc.)
        return None

    def _convert_import(self, node: ast.Import, lines: list[str]) -> Node:
        """Convert import statement."""
        content = self._get_source_segment(node, lines)
        return Node(content=content, type="import", name="import")

    def _convert_import_from(self, node: ast.ImportFrom, lines: list[str]) -> Node:
        """Convert from...import statement."""
        content = self._get_source_segment(node, lines)
        module = node.module or ""
        return Node(content=content, type="import", name=f"from_{module}")

    def _convert_class(self, node: ast.ClassDef, lines: list[str]) -> Node:
        """Convert class definition with methods as children."""
        # Build class header with decorators, name, and bases
        content_parts = []

        # Add decorators
        for decorator in node.decorator_list:
            dec_src = self._get_source_segment(decorator, lines)
            content_parts.append(f"@{dec_src}")

        # Class signature
        bases = ", ".join(self._get_source_segment(b, lines) for b in node.bases)
        if bases:
            content_parts.append(f"class {node.name}({bases}):")
        else:
            content_parts.append(f"class {node.name}:")

        # Docstring if present
        docstring = ast.get_docstring(node)
        if docstring:
            # Truncate long docstrings
            if len(docstring) > 200:
                docstring = docstring[:200] + "..."
            content_parts.append(f'    """{docstring}"""')

        content = "\n".join(content_parts)

        class_node = Node(
            content=content, type="class", name=node.name,
            source_line=node.lineno
        )

        # Add methods as children
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_node = self._convert_function(child, lines, is_method=True)
                if method_node:
                    class_node.add_child(method_node)

        return class_node

    def _convert_function(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
        lines: list[str],
        is_method: bool = False,
    ) -> Node:
        """Convert function/method definition."""
        content_parts = []

        # Add decorators
        for decorator in node.decorator_list:
            dec_src = self._get_source_segment(decorator, lines)
            content_parts.append(f"@{dec_src}")

        # Build signature
        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        args_str = self._format_arguments(node.args, lines)
        returns_str = ""
        if node.returns:
            returns_str = f" -> {self._get_source_segment(node.returns, lines)}"

        content_parts.append(f"{async_prefix}def {node.name}({args_str}){returns_str}:")

        # Skip docstrings for methods - they bloat overview
        # Class docstrings are kept (in _convert_class)
        # For detailed view, use --range to see specific methods

        content = "\n".join(content_parts)

        node_type = "method" if is_method else "function"
        return Node(content=content, type=node_type, name=node.name, source_line=node.lineno)

    def _convert_assign(self, node: ast.Assign, lines: list[str]) -> Node | None:
        """Convert module-level assignment (constants, etc.)."""
        content = self._get_source_segment(node, lines)
        # Only include if it looks like a constant (ALL_CAPS name)
        if node.targets and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper():
                return Node(content=content, type="constant", name=name)
        return None

    def _convert_annassign(self, node: ast.AnnAssign, lines: list[str]) -> Node | None:
        """Convert annotated assignment (type hints at module level)."""
        content = self._get_source_segment(node, lines)
        if isinstance(node.target, ast.Name):
            name = node.target.id
            # Include type annotations at module level
            return Node(content=content, type="annotation", name=name)
        return None

    def _format_arguments(self, args: ast.arguments, lines: list[str]) -> str:
        """Format function arguments to string."""
        parts = []

        # Regular args
        num_defaults = len(args.defaults)
        num_args = len(args.args)
        default_offset = num_args - num_defaults

        for i, arg in enumerate(args.args):
            part = arg.arg
            if arg.annotation:
                part += f": {self._get_source_segment(arg.annotation, lines)}"
            if i >= default_offset:
                default_idx = i - default_offset
                default_val = self._get_source_segment(
                    args.defaults[default_idx], lines
                )
                part += f" = {default_val}"
            parts.append(part)

        # *args
        if args.vararg:
            part = f"*{args.vararg.arg}"
            if args.vararg.annotation:
                part += f": {self._get_source_segment(args.vararg.annotation, lines)}"
            parts.append(part)

        # Keyword-only args
        for i, arg in enumerate(args.kwonlyargs):
            part = arg.arg
            if arg.annotation:
                part += f": {self._get_source_segment(arg.annotation, lines)}"
            if i < len(args.kw_defaults) and args.kw_defaults[i]:
                default_val = self._get_source_segment(args.kw_defaults[i], lines)
                part += f" = {default_val}"
            parts.append(part)

        # **kwargs
        if args.kwarg:
            part = f"**{args.kwarg.arg}"
            if args.kwarg.annotation:
                part += f": {self._get_source_segment(args.kwarg.annotation, lines)}"
            parts.append(part)

        return ", ".join(parts)

    def _get_source_segment(self, node: ast.AST, lines: list[str]) -> str:
        """Extract source code for an AST node."""
        if not hasattr(node, "lineno"):
            return ""

        start_line = node.lineno - 1
        end_line = getattr(node, "end_lineno", node.lineno) - 1
        start_col = getattr(node, "col_offset", 0)
        end_col = getattr(node, "end_col_offset", None)

        if start_line == end_line:
            # Single line
            line = lines[start_line] if start_line < len(lines) else ""
            if end_col:
                return line[start_col:end_col]
            return line[start_col:]
        else:
            # Multiple lines
            result_lines = []
            for i in range(start_line, min(end_line + 1, len(lines))):
                if i == start_line:
                    result_lines.append(lines[i][start_col:])
                elif i == end_line and end_col:
                    result_lines.append(lines[i][:end_col])
                else:
                    result_lines.append(lines[i])
            return "\n".join(result_lines)

    def rank(self, node: Node) -> float:
        """
        Return topology score for Python node.

        Hierarchy: classes > functions > methods > imports > body

        Classes and functions are primary content for code exploration.
        Imports provide context but shouldn't dominate the budget.
        """
        scores = {
            "class": 0.9,
            "function": 0.8,
            "method": 0.7,
            "constant": 0.6,
            "import": 0.5,
            "import_summary": 0.4,  # Collapsed imports - low priority
            "annotation": 0.5,
            "body": 0.4,
            "text": 0.3,
        }
        return scores.get(node.type, 0.5)

    def render(self, node: Node, budget: int) -> str | None:
        """
        Render Python node at appropriate detail level for budget.

        Progressive LOD (highest to lowest detail):
        1. Full content (signature with decorators, docstring if class)
        2. Name only (just the function/class/method name)
        3. None (fold into count)

        This enables index views where tiny budgets show scannable name lists
        instead of truncated garbage.
        """
        if budget <= 0:
            return None

        content = node.content
        name = node.name

        # Full content fits - show it all
        if len(content) <= budget:
            return content

        # For named nodes (functions, methods, classes), try name-only
        if name and node.type in ("function", "method", "class", "constant", "annotation"):
            # Name needs at least enough space for the name itself
            if len(name) <= budget:
                return name
            # Name too long - truncate it
            if budget >= 4:
                return name[:budget - 3] + "..."

        # For import summaries, keep as-is (already compact)
        if node.type == "import_summary":
            if budget >= 10:
                # Show truncated summary like "[58 imp...]"
                return content[:budget - 3] + "..."
            return None

        # Fallback: truncate content (preserves partial signatures)
        if budget >= 10:
            return content[:budget - 3] + "..."

        # Budget too small for anything useful
        return None


# Register the strategy
registry.register(PythonStrategy())
