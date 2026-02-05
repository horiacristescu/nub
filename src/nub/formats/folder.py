"""
Folder format strategy.

Treats directories as navigable content with hierarchical structure.
Files show content previews (head-truncated), directories show structure.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..dom import Node
from .base import FormatStrategy, registry


class FolderStrategy(FormatStrategy):
    """Directory/folder format handler with content previews."""

    # Common patterns to skip by default (caches, build artifacts)
    DEFAULT_SKIP_PATTERNS = frozenset({
        "__pycache__",
        ".git",
        ".svn",
        ".hg",
        "node_modules",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pypackages__",
        ".eggs",
        "*.egg-info",
        ".DS_Store",
    })

    # Binary file extensions to skip reading
    BINARY_EXTENSIONS = frozenset({
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".bmp",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib",
        ".pyc", ".pyo", ".class",
        ".woff", ".woff2", ".ttf", ".eot",
        ".mp3", ".mp4", ".wav", ".ogg", ".webm", ".avi", ".mov",
        ".sqlite", ".db",
    })

    def __init__(
        self,
        max_depth: int = 10,
        follow_symlinks: bool = False,
        skip_patterns: frozenset[str] | None = None,
        preview_chars: int = 200,
        max_read_bytes: int = 10240,  # 10KB max read per file
        indent: str = "  ",  # 2 spaces per level
    ):
        """
        Initialize folder strategy.

        Args:
            max_depth: Maximum directory depth to traverse
            follow_symlinks: Whether to follow symbolic links (risky - can loop)
            skip_patterns: Patterns to skip (defaults to common caches/artifacts)
            preview_chars: Max characters to show in preview
            max_read_bytes: Max bytes to read from each file
            indent: Indentation string per depth level
        """
        self._max_depth = max_depth
        self._follow_symlinks = follow_symlinks
        self._skip_patterns = skip_patterns if skip_patterns is not None else self.DEFAULT_SKIP_PATTERNS
        self._preview_chars = preview_chars
        self._max_read_bytes = max_read_bytes
        self._indent = indent

    @property
    def name(self) -> str:
        return "folder"

    @property
    def extensions(self) -> list[str]:
        return []  # Directories don't have extensions

    def parse(self, content: str) -> Node:
        """
        Not used for folders - use parse_path() instead.

        This method exists to satisfy the interface but shouldn't be called
        for folder content.
        """
        raise NotImplementedError(
            "FolderStrategy requires parse_path() instead of parse()"
        )

    def parse_path(self, path: str) -> Node:
        """
        Parse a directory path into a hierarchical node structure.

        Args:
            path: Path to directory

        Returns:
            Root node representing the directory tree
        """
        path_obj = Path(path)

        if not path_obj.exists():
            raise FileNotFoundError(f"Path does not exist: {path}")

        if not path_obj.is_dir():
            raise ValueError(f"Path is not a directory: {path}")

        return self._parse_directory(path_obj, depth=0)

    def _parse_directory(self, path: Path, depth: int) -> Node:
        """
        Recursively parse a directory into nodes.

        Args:
            path: Directory path
            depth: Current recursion depth

        Returns:
            Node representing this directory and its contents
        """
        dir_name = path.name or str(path)  # Use full path if name is empty (root)
        indent_prefix = self._indent * depth

        # Create directory node with indented name and trailing slash
        dir_node = Node(
            content=f"{indent_prefix}{dir_name}/",
            type="directory",
            name=dir_name
        )

        # Stop if we've hit max depth
        if depth >= self._max_depth:
            return dir_node

        # List directory contents
        try:
            entries = sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name))
        except PermissionError:
            # Can't read directory - return empty node
            return dir_node

        for entry in entries:
            # Skip symlinks unless following is enabled
            if entry.is_symlink() and not self._follow_symlinks:
                continue

            # Skip common cache/artifact patterns
            if self._should_skip(entry.name):
                continue

            if entry.is_dir():
                # Recursively parse subdirectory
                child_node = self._parse_directory(entry, depth + 1)
                dir_node.add_child(child_node)
            elif entry.is_file():
                # Add file node with content preview
                file_node = self._parse_file(entry, depth + 1)
                if file_node:
                    dir_node.add_child(file_node)

        return dir_node

    def _parse_file(self, path: Path, depth: int) -> Node | None:
        """
        Parse a file into a node with content preview.

        Args:
            path: Path to file
            depth: Depth for indentation

        Returns:
            File node with preview, or None if can't read
        """
        try:
            file_size = path.stat().st_size
        except (PermissionError, OSError):
            return None

        indent_prefix = self._indent * depth
        size_str = self._format_size(file_size)

        # Check if binary
        if self._is_binary(path):
            content = f"{indent_prefix}{path.name} [binary] [{size_str}]"
            return Node(
                content=content,
                type="file",
                name=path.name,
                atomic=True,  # Binary marker is fixed - don't middle-drop
            )

        # Try to read and create preview
        preview = self._read_preview(path)

        if preview:
            # Format: indent + name - preview [size]
            # No [...] marker - the preview is already head-truncated
            content = f"{indent_prefix}{path.name} - {preview} [{size_str}]"
        else:
            # Can't read or empty - show name and size only
            content = f"{indent_prefix}{path.name} [{size_str}]"

        return Node(
            content=content,
            type="file",
            name=path.name,
            atomic=True,  # Preview is already optimized - don't middle-drop
        )

    def _read_preview(self, path: Path) -> str | None:
        """
        Read file head and create collapsed single-line preview.

        Returns collapsed preview string, or None if can't read.
        """
        try:
            # Read limited bytes
            raw_bytes = path.read_bytes()[:self._max_read_bytes]

            # Try UTF-8 decode
            try:
                text = raw_bytes.decode("utf-8")
            except UnicodeDecodeError:
                # Try latin-1 as fallback
                try:
                    text = raw_bytes.decode("latin-1")
                except UnicodeDecodeError:
                    return None

            # Collapse whitespace: newlines, tabs, multiple spaces -> single space
            collapsed = re.sub(r'\s+', ' ', text).strip()

            # Head-truncate to preview_chars
            if len(collapsed) > self._preview_chars:
                collapsed = collapsed[:self._preview_chars]

            return collapsed if collapsed else None

        except (PermissionError, OSError):
            return None

    def _is_binary(self, path: Path) -> bool:
        """Check if file is likely binary based on extension."""
        return path.suffix.lower() in self.BINARY_EXTENSIONS

    def _should_skip(self, name: str) -> bool:
        """Check if entry should be skipped based on patterns."""
        if name in self._skip_patterns:
            return True
        # Check glob-style patterns (e.g., *.egg-info)
        for pattern in self._skip_patterns:
            if pattern.startswith("*") and name.endswith(pattern[1:]):
                return True
        return False

    def _format_size(self, size_bytes: int) -> str:
        """
        Format file size in human-readable form.

        Args:
            size_bytes: Size in bytes

        Returns:
            Formatted string (e.g., "2.3 KB", "120 bytes")
        """
        if size_bytes < 1024:
            return f"{size_bytes} bytes"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes / (1024 * 1024):.1f} MB"
        else:
            return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"

    def rank(self, node: Node) -> float:
        """
        Return topology score for a node.

        Directories rank higher than files (structure > content).
        Within files, could rank by size, but keeping it simple for now.
        """
        if node.type == "directory":
            # Directories are structure - high importance
            return 0.8
        elif node.type == "file":
            # Files are content - medium importance
            return 0.5
        else:
            # Default
            return 0.5


# Register the strategy
registry.register(FolderStrategy())
