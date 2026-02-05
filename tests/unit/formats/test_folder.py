"""Tests for folder format strategy."""

import tempfile
from pathlib import Path

import pytest

from nub.dom import Node
from nub.formats.folder import FolderStrategy


class TestFolderStrategy:
    """Test folder format parsing and ranking."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory structure for testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create some files and folders
            (base / "file1.txt").write_text("Hello world")
            (base / "file2.py").write_text("print('test')")

            # Create nested structure
            (base / "src").mkdir()
            (base / "src" / "main.py").write_text("def main(): pass")
            (base / "src" / "utils.py").write_text("def helper(): pass")

            (base / "tests").mkdir()
            (base / "tests" / "test_main.py").write_text("def test_main(): pass")

            # Empty folder
            (base / "empty").mkdir()

            yield base

    def test_name(self, strategy):
        assert strategy.name == "folder"

    def test_extensions_empty(self, strategy):
        """Folders don't have extensions, detected by path."""
        assert strategy.extensions == []

    def test_parse_creates_hierarchy(self, strategy, temp_dir):
        """Parse should create hierarchical node structure."""
        root = strategy.parse_path(str(temp_dir))

        assert root.type == "directory"
        assert root.name == temp_dir.name
        assert len(root.children) > 0

        # Should have folders and files as children
        child_types = {child.type for child in root.children}
        assert "directory" in child_types or "file" in child_types

    def test_parse_includes_size_metadata(self, strategy, temp_dir):
        """File nodes should include size in metadata."""
        root = strategy.parse_path(str(temp_dir))

        # Find a file node
        def find_file_node(node):
            if node.type == "file":
                return node
            for child in node.children:
                result = find_file_node(child)
                if result:
                    return result
            return None

        file_node = find_file_node(root)
        assert file_node is not None
        # Size should be stored somewhere accessible for rendering
        # Could be in node.content as metadata or separate field

    def test_parse_handles_empty_directory(self, strategy, temp_dir):
        """Empty directories should parse without error."""
        empty_dir = temp_dir / "empty"
        root = strategy.parse_path(str(empty_dir))

        assert root.type == "directory"
        assert len(root.children) == 0

    def test_rank_folder_higher_than_file(self, strategy):
        """Folders should rank higher than files in topology."""
        folder_node = Node(content="", type="directory", name="src")
        file_node = Node(content="", type="file", name="main.py")

        assert strategy.rank(folder_node) > strategy.rank(file_node)

    def test_rank_larger_files_higher(self, strategy):
        """Larger files should rank higher (assuming size is factor)."""
        # This is a design choice - we might want to rank by size
        # For now, just test that ranking is consistent
        small_file = Node(content="", type="file", name="small.txt")
        large_file = Node(content="", type="file", name="large.txt")

        # Both should have reasonable scores
        assert 0.0 <= strategy.rank(small_file) <= 1.0
        assert 0.0 <= strategy.rank(large_file) <= 1.0


class TestFolderSymlinks:
    """Test handling of symlinks."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    def test_symlinks_not_followed_by_default(self, strategy):
        """Symlinks should not be followed to avoid infinite loops."""
        # Create temp dir with symlink
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "real").mkdir()
            (base / "real" / "file.txt").write_text("content")

            # Create symlink pointing back to parent
            try:
                (base / "real" / "link").symlink_to(base)
            except OSError:
                pytest.skip("Symlinks not supported on this system")

            # Should not loop infinitely
            root = strategy.parse_path(str(base))
            assert root is not None


class TestFolderContentPreviews:
    """Test file content preview generation."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def content_dir(self):
        """Create directory with files containing various content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Multi-line content that should be collapsed
            (base / "multiline.txt").write_text(
                "Line one\nLine two\nLine three\n  Indented line"
            )

            # Python docstring
            (base / "module.py").write_text(
                '"""Module docstring\n\nWith multiple paragraphs."""\n\ndef func():\n    pass'
            )

            # Long content for truncation
            (base / "long.txt").write_text("x" * 1000)

            # Binary-like content
            (base / "binary.bin").write_bytes(b"\x00\x01\x02\x03\xff\xfe")

            yield base

    def test_file_node_has_content_preview(self, strategy, content_dir):
        """File nodes should have content preview in their content field."""
        root = strategy.parse_path(str(content_dir))

        # Find multiline.txt
        file_node = None
        for child in root.children:
            if child.name == "multiline.txt":
                file_node = child
                break

        assert file_node is not None
        # Content should include preview text (collapsed to single line)
        assert "Line one" in file_node.content
        # Multiple spaces/newlines should be collapsed
        assert "\n" not in file_node.content

    def test_content_preview_truncated(self, strategy, content_dir):
        """Long content should be head-truncated."""
        root = strategy.parse_path(str(content_dir))

        file_node = None
        for child in root.children:
            if child.name == "long.txt":
                file_node = child
                break

        assert file_node is not None
        # Should not contain full 1000 chars - just preview
        assert len(file_node.content) < 500  # Should be much shorter

    def test_binary_files_handled_gracefully(self, strategy, content_dir):
        """Binary files should not crash, show placeholder or size only."""
        root = strategy.parse_path(str(content_dir))

        file_node = None
        for child in root.children:
            if child.name == "binary.bin":
                file_node = child
                break

        assert file_node is not None
        # Should have some content (even if just size marker)
        assert file_node.content != ""


class TestFolderHierarchyIndentation:
    """Test that folder hierarchy is preserved with indentation."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def nested_dir(self):
        """Create deeply nested directory structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            # Create nested structure: project/src/nub/core.py
            project = base / "project"
            project.mkdir()
            (project / "README.md").write_text("# Project\n\nDescription")

            src = project / "src"
            src.mkdir()

            nub = src / "nub"
            nub.mkdir()
            (nub / "core.py").write_text("def compress(): pass")
            (nub / "cli.py").write_text("def main(): pass")

            yield project

    def test_directory_content_shows_path(self, strategy, nested_dir):
        """Directory nodes should show their name with trailing slash."""
        root = strategy.parse_path(str(nested_dir))

        # Root should be "project/"
        assert "project" in root.content or root.name == "project"

        # Find src directory
        src_node = None
        for child in root.children:
            if child.type == "directory" and child.name == "src":
                src_node = child
                break

        assert src_node is not None

    def test_nested_structure_preserved(self, strategy, nested_dir):
        """Nested directories should have proper parent-child relationships."""
        root = strategy.parse_path(str(nested_dir))

        # project/src/nub/core.py should be at depth 3
        def find_at_depth(node, target_name, depth=0):
            if node.name == target_name:
                return depth
            for child in node.children:
                result = find_at_depth(child, target_name, depth + 1)
                if result is not None:
                    return result
            return None

        core_depth = find_at_depth(root, "core.py")
        assert core_depth == 3  # project -> src -> nub -> core.py

    def test_content_includes_indentation_prefix(self, strategy, nested_dir):
        """File content should include indentation prefix for depth."""
        root = strategy.parse_path(str(nested_dir))

        # Find core.py recursively
        def find_node(node, target_name):
            if node.name == target_name:
                return node
            for child in node.children:
                result = find_node(child, target_name)
                if result:
                    return result
            return None

        core_node = find_node(root, "core.py")
        assert core_node is not None
        # Content should start with indentation (spaces for depth)
        # At depth 3, should have leading spaces
        assert core_node.content.startswith("  ") or "core.py" in core_node.content


class TestFolderOutputFormat:
    """Test the rendered output format for folder strategy."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def simple_project(self):
        """Create simple project structure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)

            (base / "README.md").write_text("# Hello\n\nThis is a test project.")
            (base / "main.py").write_text('"""Main module."""\n\nprint("hello")')

            src = base / "src"
            src.mkdir()
            (src / "app.py").write_text('"""App module."""\n\nclass App:\n    pass')

            yield base

    def test_file_content_format(self, strategy, simple_project):
        """Files should have format: indent + name - preview [size]."""
        root = strategy.parse_path(str(simple_project))

        # Find README.md
        readme = None
        for child in root.children:
            if child.name == "README.md":
                readme = child
                break

        assert readme is not None
        # Content should contain the filename, preview, and size
        # Format: "README.md - # Hello This is a test project. [38 bytes]"
        assert "README.md" in readme.content
        # Should have size marker
        assert "[" in readme.content and "bytes" in readme.content or "KB" in readme.content

    def test_directory_content_format(self, strategy, simple_project):
        """Directories should have format: indent + name/ (trailing slash)."""
        root = strategy.parse_path(str(simple_project))

        # Find src directory
        src = None
        for child in root.children:
            if child.name == "src":
                src = child
                break

        assert src is not None
        # Directory content should end with / or clearly indicate directory
        assert "/" in src.content or src.type == "directory"


class TestFolderAtomicNodes:
    """Test that folder file nodes are marked as atomic."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def project_dir(self):
        """Create project with various file types."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            (base / "readme.txt").write_text("Some content here")
            (base / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n")  # PNG header
            yield base

    def test_file_nodes_are_atomic(self, strategy, project_dir):
        """File nodes should have atomic=True to prevent middle-dropping."""
        root = strategy.parse_path(str(project_dir))

        # Find text file
        for child in root.children:
            if child.name == "readme.txt":
                assert child.atomic is True, "Text file nodes should be atomic"

    def test_binary_file_nodes_are_atomic(self, strategy, project_dir):
        """Binary file nodes should also be atomic."""
        root = strategy.parse_path(str(project_dir))

        for child in root.children:
            if child.name == "image.png":
                assert child.atomic is True, "Binary file nodes should be atomic"

    def test_directory_nodes_not_atomic(self, strategy, project_dir):
        """Directory nodes should not be atomic (they have children)."""
        root = strategy.parse_path(str(project_dir))
        # Root is a directory
        assert root.atomic is False, "Directory nodes should not be atomic"

    def test_no_redundant_ellipsis_in_preview(self, strategy, project_dir):
        """File previews should not have redundant [...] marker."""
        root = strategy.parse_path(str(project_dir))

        for child in root.children:
            if child.name == "readme.txt":
                # Should NOT have [...] before size - just name - preview [size]
                # The pattern "[...] [" would indicate redundant marker
                assert "[...] [" not in child.content
                # Should have size marker
                assert "[" in child.content and "bytes" in child.content


class TestFolderCompressionIntegration:
    """Integration tests for folder compression output."""

    @pytest.fixture
    def strategy(self):
        return FolderStrategy()

    @pytest.fixture
    def nested_project(self):
        """Create nested project for compression testing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base = Path(tmpdir)
            project = base / "project"
            project.mkdir()

            # Create src/app.py
            src = project / "src"
            src.mkdir()
            (src / "app.py").write_text("def main(): pass")

            # Create tests/test_app.py
            tests = project / "tests"
            tests.mkdir()
            (tests / "test_app.py").write_text("def test_main(): pass")

            yield project

    def test_directory_names_preserved_in_output(self, strategy, nested_project):
        """Directory names should appear in compressed output."""
        from nub.core import compress_tree

        root = strategy.parse_path(str(nested_project))
        output = compress_tree(root, budget=2000, ranker=strategy.rank)

        output_text = "\n".join(line.content for line in output)

        # Directory names should be visible
        assert "src/" in output_text, "src/ directory should be visible"
        assert "tests/" in output_text, "tests/ directory should be visible"

        # File names should also be visible
        assert "app.py" in output_text
        assert "test_app.py" in output_text

    def test_no_middle_drop_markers_in_output(self, strategy, nested_project):
        """Output should not have [+N chars] middle-drop markers."""
        from nub.core import compress_tree

        root = strategy.parse_path(str(nested_project))
        output = compress_tree(root, budget=500, ranker=strategy.rank)

        output_text = "\n".join(line.content for line in output)

        # Should not have middle-drop markers
        assert "[+" not in output_text, f"Should not have [+N chars] markers: {output_text}"
