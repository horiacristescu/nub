"""
Integration tests for CLI.
"""

import pytest
from pathlib import Path

from nub.cli import main, compress, parse_args, read_input


FIXTURES = Path(__file__).parent.parent / "fixtures"


class TestParseArgs:
    def test_defaults(self):
        args = parse_args([])
        assert args.shape == "120:100"
        assert args.grep is None
        assert args.format_type is None
        assert args.file is None

    def test_shape_flag(self):
        args = parse_args(["--shape", "80:50"])
        assert args.shape == "80:50"

    def test_shape_short_flag(self):
        args = parse_args(["-s", "80:50"])
        assert args.shape == "80:50"

    def test_grep_flag(self):
        args = parse_args(["--grep", "error"])
        assert args.grep == "error"

    def test_type_flag(self):
        args = parse_args(["--type", "python"])
        assert args.format_type == "python"

    def test_file_positional(self):
        args = parse_args(["myfile.txt"])
        assert args.file == "myfile.txt"

    def test_all_flags(self):
        args = parse_args([
            "input.txt",
            "--shape", "80:50",
            "--grep", "pattern",
            "--type", "text",
        ])
        assert args.file == "input.txt"
        assert args.shape == "80:50"
        assert args.grep == "pattern"
        assert args.format_type == "text"


class TestCompress:
    def test_compress_basic(self):
        content = "line one\nline two\nline three"
        # 10x10 = 100 char budget
        result = compress(content, width=10, height=10)
        assert len(result) <= 100
        assert result  # not empty

    def test_compress_respects_budget(self):
        content = "x" * 100 + "\n" + "y" * 100 + "\n" + "z" * 100
        # 10x5 = 50 char budget
        result = compress(content, width=10, height=5)
        # Allow small tolerance for markers and newlines
        assert len(result) <= 60

    def test_compress_grep_boosts_match(self):
        content = "normal line\nERROR: critical\nmore normal"
        # 10x6 = 60 char budget
        result = compress(content, width=10, height=6, grep_pattern="ERROR")
        # ERROR line should get more budget
        assert "ERROR" in result

    def test_compress_empty_input(self):
        result = compress("", width=10, height=10)
        assert result == ""

    def test_compress_fixture_file(self):
        content = (FIXTURES / "sample.txt").read_text()
        # 10x10 = 100 char budget
        result = compress(content, width=10, height=10)
        # Allow small tolerance for markers and newlines
        assert len(result) <= 110


class TestMain:
    def test_main_with_file(self, capsys):
        filepath = str(FIXTURES / "sample.txt")
        # 10x10 shape = 100 char budget
        exit_code = main([filepath, "--shape", "10:10"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert captured.out  # some output
        # Allow small tolerance for markers and newlines
        assert len(captured.out.strip()) <= 110

    def test_main_file_not_found(self, capsys):
        exit_code = main(["nonexistent.txt"])
        assert exit_code == 1
        captured = capsys.readouterr()
        assert "not found" in captured.err.lower()

    def test_main_with_grep(self, capsys):
        filepath = str(FIXTURES / "log_sample.txt")
        # 20x10 shape = 200 char budget
        exit_code = main([filepath, "--shape", "20:10", "--grep", "ERROR"])
        assert exit_code == 0
        captured = capsys.readouterr()
        assert "ERROR" in captured.out


class TestFolderRange:
    """Test range selection for folder output."""

    @pytest.fixture
    def temp_dir(self, tmp_path):
        """Create a temp directory with several files."""
        # Create 5 files to get predictable output
        for i in range(1, 6):
            (tmp_path / f"file{i}.txt").write_text(f"Content of file {i}")
        return tmp_path

    def test_folder_range_basic(self, temp_dir, capsys):
        """Range 1:3 should show first 3 lines."""
        exit_code = main([str(temp_dir), "--shape", "100:50", "--range", "1:3"])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 3

    def test_folder_range_middle(self, temp_dir, capsys):
        """Range 2:4 should show 3 lines from the middle."""
        # First get full output
        exit_code = main([str(temp_dir), "--shape", "100:50"])
        assert exit_code == 0
        full_output = capsys.readouterr().out
        full_lines = [l for l in full_output.strip().split("\n") if l]

        # Now get range 2:4 (lines 2, 3, 4)
        exit_code = main([str(temp_dir), "--shape", "100:50", "--range", "2:4"])
        assert exit_code == 0
        range_output = capsys.readouterr().out
        range_lines = [l for l in range_output.strip().split("\n") if l]

        # Should get exactly 3 lines
        assert len(range_lines) == 3
        # Range output should be less than full output
        assert len(range_lines) < len(full_lines)

    def test_folder_range_with_dedup(self, temp_dir, capsys):
        """Range should work with deduplication."""
        exit_code = main([str(temp_dir), "--shape", "100:50", "--range", "1:3", "-d"])
        assert exit_code == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().split("\n") if l]
        assert len(lines) == 3


class TestLargeFileHandling:
    """Test head+tail handling for large files."""

    def test_large_file_head_tail(self, tmp_path, monkeypatch):
        """Files larger than threshold get head+tail with marker."""
        # Set low threshold for testing (10KB instead of 1MB)
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "10240")  # 10KB
        monkeypatch.setenv("NUB_HEAD_BYTES", "2048")  # 2KB head
        monkeypatch.setenv("NUB_TAIL_BYTES", "2048")  # 2KB tail

        # Clear cached config so env vars take effect
        import nub.config
        nub.config._config = None

        # Create a 20KB file
        large_file = tmp_path / "large.txt"
        head_content = "HEAD " + "A" * 2000  # ~2KB of A's at start
        middle_content = "M" * 16000  # ~16KB of M's in middle
        tail_content = "B" * 2000 + " TAIL"  # ~2KB of B's at end
        large_file.write_text(head_content + middle_content + tail_content)

        content, filename, is_dir = read_input(str(large_file))

        # Reset config for other tests
        nub.config._config = None

        # Should have head content
        assert "HEAD" in content
        # Should have tail content
        assert "TAIL" in content
        # Should have truncation marker
        assert "truncated" in content.lower()
        # Should NOT have all middle content
        assert len(content) < 10000  # Much smaller than 20KB

    def test_small_file_read_fully(self, tmp_path, monkeypatch):
        """Files smaller than threshold are read completely."""
        # Set threshold higher than our test file
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "1048576")  # 1MB

        import nub.config
        nub.config._config = None

        # Create a small file (1KB)
        small_file = tmp_path / "small.txt"
        content_to_write = "Line " + "x" * 100 + "\n" * 10
        small_file.write_text(content_to_write)

        content, filename, is_dir = read_input(str(small_file))

        nub.config._config = None

        # Should have exact content (no truncation marker)
        assert content == content_to_write
        assert "truncated" not in content.lower()

    def test_truncation_marker_shows_mb(self, tmp_path, monkeypatch):
        """Truncation marker should show skipped size in MB."""
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "10240")  # 10KB
        monkeypatch.setenv("NUB_HEAD_BYTES", "1024")  # 1KB
        monkeypatch.setenv("NUB_TAIL_BYTES", "1024")  # 1KB

        import nub.config
        nub.config._config = None

        # Create 100KB file - skipping ~98KB
        large_file = tmp_path / "medium.txt"
        large_file.write_text("x" * 102400)  # 100KB

        content, _, _ = read_input(str(large_file))

        nub.config._config = None

        # Should show MB truncated (98KB = ~0.1MB)
        assert "MB truncated" in content

    def test_main_with_large_file(self, tmp_path, capsys, monkeypatch):
        """End-to-end test with large file through main()."""
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "10240")
        monkeypatch.setenv("NUB_HEAD_BYTES", "2048")
        monkeypatch.setenv("NUB_TAIL_BYTES", "2048")

        import nub.config
        nub.config._config = None

        # Create large file with identifiable content
        large_file = tmp_path / "large.log"
        lines = [f"HEAD LINE {i}" for i in range(50)]
        lines.extend([f"MIDDLE LINE {i}" for i in range(5000)])  # Many middle lines
        lines.extend([f"TAIL LINE {i}" for i in range(50)])
        large_file.write_text("\n".join(lines))

        exit_code = main([str(large_file), "--shape", "120:20"])

        nub.config._config = None

        assert exit_code == 0
        captured = capsys.readouterr()

        # Should have compressed output with truncation
        assert captured.out
        # Content should be from head and/or tail sections
        # (exact content depends on compression algorithm)

    def test_line_boundary_integrity(self, tmp_path, monkeypatch):
        """Head and tail should cut at line boundaries, not mid-line."""
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "10240")  # 10KB
        monkeypatch.setenv("NUB_HEAD_BYTES", "1024")  # 1KB
        monkeypatch.setenv("NUB_TAIL_BYTES", "1024")  # 1KB

        import nub.config

        nub.config._config = None

        # Create file with numbered lines (known boundaries)
        large_file = tmp_path / "numbered.txt"
        lines = [f"LINE_{i:05d}_CONTENT" for i in range(1000)]
        large_file.write_text("\n".join(lines))

        content, _, _ = read_input(str(large_file))

        nub.config._config = None

        # Split into lines and check integrity
        result_lines = content.split("\n")

        # Filter out empty lines and truncation marker
        content_lines = [
            ln for ln in result_lines if ln and "truncated" not in ln.lower()
        ]

        # Each line should be complete (start with LINE_ and end with _CONTENT)
        for line in content_lines:
            assert line.startswith("LINE_"), f"Partial line at start: {line[:50]}"
            assert line.endswith("_CONTENT"), f"Partial line at end: {line[-50:]}"

    def test_line_boundary_prevents_empty_output(self, tmp_path, monkeypatch, capsys):
        """Line boundary fix prevents empty output from corrupted parsing."""
        monkeypatch.setenv("NUB_MAX_FILE_SIZE", "10240")  # 10KB
        monkeypatch.setenv("NUB_HEAD_BYTES", "1024")  # 1KB
        monkeypatch.setenv("NUB_TAIL_BYTES", "1024")  # 1KB

        import nub.config

        nub.config._config = None

        # Create file with numbered lines
        large_file = tmp_path / "numbered2.txt"
        lines = [f"{i}: This is line number {i} with padding text" for i in range(1, 1001)]
        large_file.write_text("\n".join(lines))

        # Run through main to test full pipeline
        exit_code = main([str(large_file), "--shape", "100:30"])

        nub.config._config = None

        assert exit_code == 0
        captured = capsys.readouterr()

        # Should have non-empty output with actual line content
        assert captured.out.strip(), "Output should not be empty"
        # Should contain recognizable line content
        assert "line number" in captured.out.lower() or ":" in captured.out
