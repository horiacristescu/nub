"""
CLI interface for Nub.

Pipe-friendly compression tool with format detection and budget control.
"""

from __future__ import annotations

import argparse
import re
import sys

from .config import get_config
from .core import OutputLine, compress_tree, deduplicate_3grams
from .formats import (
    folder as _folder,  # noqa: F401 - ensure folder format is registered
)
from .formats import (
    markdown as _markdown,  # noqa: F401 - ensure markdown format is registered
)
from .formats import (
    mindmap as _mindmap,  # noqa: F401 - ensure mindmap format is registered
)
from .formats import (
    python as _python,  # noqa: F401 - ensure python format is registered
)
from .formats import text as _text  # noqa: F401 - ensure text format is registered
from .formats.base import FormatStrategy, registry
from .formats.folder import FolderStrategy
from .formats.text import CustomSeparatorStrategy


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    get_config()

    parser = argparse.ArgumentParser(
        prog="nub",
        description="Smart context compression for AI agents",
    )

    parser.add_argument(
        "file",
        nargs="?",
        help="Input file (reads from stdin if not provided)",
    )

    parser.add_argument(
        "--shape",
        "-s",
        type=str,
        default="120:100",
        help="Output shape as WIDTH:HEIGHT (e.g., 120:100 for 120 chars × 100 lines)",
    )

    parser.add_argument(
        "--wrap",
        "-w",
        type=int,
        help="Wrap long lines at this width, creating fractional line addresses",
    )

    parser.add_argument(
        "--range",
        "-r",
        type=str,
        help="Line range (supports fractional: 1.0:5.50, 100:200, or 42.25:42.75)",
    )

    parser.add_argument(
        "--no-line-numbers",
        "-N",
        action="store_false",
        dest="line_numbers",
        default=True,
        help="Disable line numbers (shown by default)",
    )

    parser.add_argument(
        "--grep",
        "-g",
        type=str,
        help="Regex pattern to boost matching lines",
    )

    parser.add_argument(
        "--separator",
        type=str,
        help="Split content by this separator instead of newlines (e.g., '---' for messages)",
    )

    parser.add_argument(
        "--separator-regex",
        type=str,
        help="Split content by regex pattern (e.g., '^---$' for message boundaries)",
    )

    parser.add_argument(
        "--profile",
        "-p",
        action="store_true",
        help="Profile file to detect state features and recommend exploration policy",
    )

    parser.add_argument(
        "--deduplicate",
        "-d",
        action="store_true",
        help="Remove repeated 3-word sequences to reduce redundancy",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=10000,
        help="Maximum output characters (default: 10000). Shows first 10K chars + message if exceeded",
    )

    parser.add_argument(
        "--type",
        type=str,
        dest="format_type",
        help="Force format type (e.g., text, python, json)",
    )

    # Legacy compatibility (hidden)
    parser.add_argument(
        "--target",
        "-t",
        type=int,
        help=argparse.SUPPRESS,  # Hidden legacy option
    )

    parser.add_argument(
        "--temperature",
        type=float,
        help=argparse.SUPPRESS,  # Internal parameter, not exposed
    )

    return parser.parse_args(args)


def read_input(filepath: str | None) -> tuple[str, str | None, bool]:
    """
    Read from file or stdin, return (content, filename, is_directory).

    For directories, content will be empty string and is_directory will be True.
    For large files (>1MB by default), reads first 500KB + last 500KB with truncation marker.
    """
    import os

    if filepath:
        if os.path.isdir(filepath):
            # Directory path - will be handled specially
            return "", filepath, True

        cfg = get_config()
        file_size = os.path.getsize(filepath)

        if file_size > cfg.io.max_file_size:
            # Large file: read head + tail with line-boundary alignment
            with open(filepath, "rb") as f:
                # Read head and trim to last complete line
                head = f.read(cfg.io.head_bytes)
                last_newline = head.rfind(b"\n")
                if last_newline != -1:
                    head = head[: last_newline + 1]
                    head_end_pos = last_newline + 1
                else:
                    head_end_pos = len(head)

                # Seek to tail position and align to line boundary
                tail_start = max(0, file_size - cfg.io.tail_bytes)
                if tail_start > head_end_pos:
                    f.seek(tail_start)
                    # Find next newline to start at a complete line
                    chunk = f.read(1024)
                    newline_pos = chunk.find(b"\n")
                    if newline_pos != -1:
                        # Start just after the newline
                        tail_start = tail_start + newline_pos + 1
                    f.seek(tail_start)
                    tail = f.read()
                else:
                    # Tail overlaps with head - just read from after head
                    f.seek(head_end_pos)
                    tail = f.read()
                    tail_start = head_end_pos

            # Decode with replacement for invalid bytes
            head_str = head.decode("utf-8", errors="replace")
            tail_str = tail.decode("utf-8", errors="replace")

            # Calculate skipped bytes (between head end and tail start)
            skipped_bytes = max(0, tail_start - head_end_pos)
            skipped_mb = skipped_bytes / (1024 * 1024)

            # Insert truncation marker (only if there's actually a gap)
            if skipped_bytes > 0:
                marker = f"\n[...{skipped_mb:.1f} MB truncated...]\n\n"
                content = head_str + marker + tail_str
            else:
                content = head_str + tail_str

            return content, filepath, False

        # Small file: read normally
        with open(filepath, encoding="utf-8") as f:
            return f.read(), filepath, False

    return sys.stdin.read(), None, False


def parse_shape(shape_str: str) -> tuple[int, int]:
    """
    Parse shape string like '120:100' into (width, height).
    Returns (chars_per_line, num_lines).
    """
    parts = shape_str.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid shape format: {shape_str}. Use WIDTH:HEIGHT (e.g., 120:100)"
        )

    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as e:
        raise ValueError(
            f"Invalid shape format: {shape_str}. Both WIDTH and HEIGHT must be integers"
        ) from e

    if width < 1:
        raise ValueError(f"Width must be >= 1, got {width}")
    if height < 1:
        raise ValueError(f"Height must be >= 1, got {height}")

    return width, height


def parse_range(range_str: str | None) -> tuple[float | None, float | None]:
    """
    Parse range string supporting fractional line numbers.
    Examples: '1.0:5.0', '100:200', '1.25:1.75'
    Returns (None, None) if no range specified.
    """
    if not range_str:
        return None, None

    parts = range_str.split(":")
    if len(parts) != 2:
        raise ValueError(
            f"Invalid range format: {range_str}. Use START:END (e.g., 1.0:5.0 or 100:200)"
        )

    try:
        start = float(parts[0])
        end = float(parts[1])
    except ValueError as e:
        raise ValueError(
            f"Invalid range format: {range_str}. START and END must be numbers"
        ) from e

    if start < 1.0:
        raise ValueError(f"Start line must be >= 1.0, got {start}")
    if end < start:
        raise ValueError(f"End line must be >= start line, got {start}:{end}")

    return start, end


def wrap_content(content: str, wrap_width: int, add_line_nums: bool = False) -> str:
    """
    Wrap long lines at wrap_width, creating fractional line addresses.

    Args:
        content: Original content
        wrap_width: Width to wrap at
        add_line_nums: Whether to add line number prefixes

    Returns:
        Content with wrapped lines, optionally with fractional addresses as prefixes
    """
    original_lines = content.split("\n")
    wrapped_lines = []

    for line_num, line in enumerate(original_lines, start=1):
        line_len = len(line)

        if line_len <= wrap_width:
            # Short line, no wrapping needed
            if add_line_nums:
                wrapped_lines.append(f"{line_num}: {line}")
            else:
                wrapped_lines.append(line)
        else:
            # Long line, needs wrapping
            num_segments = (line_len + wrap_width - 1) // wrap_width  # ceil division
            for seg_idx in range(num_segments):
                start_char = seg_idx * wrap_width
                end_char = min(start_char + wrap_width, line_len)
                segment = line[start_char:end_char]

                # Calculate percentage (0-99)
                percentage = int((start_char / line_len) * 100)

                if add_line_nums:
                    address = f"{line_num}.{percentage:02d}"
                    wrapped_lines.append(f"{address}: {segment}")
                else:
                    wrapped_lines.append(segment)

    return "\n".join(wrapped_lines)


def extract_fractional_range(
    content: str, start: float | None, end: float | None
) -> str:
    """
    Extract lines based on fractional line addresses.

    Args:
        content: Content with fractional addresses (e.g., "1.00: text", "1.25: more")
        start: Start address (e.g., 1.25)
        end: End address (e.g., 3.75)

    Returns:
        Filtered content containing only lines in the range
    """
    if start is None or end is None:
        return content

    lines = content.split("\n")
    result_lines = []

    for line in lines:
        # Try to parse fractional address from line
        # Format: "1.25: content" or "42: content"
        match = re.match(r"^(\d+(?:\.\d+)?): ", line)
        if match:
            address = float(match.group(1))
            if start <= address <= end:
                result_lines.append(line)
        else:
            # If no address prefix, keep the line if we're in range 1.0+
            if start <= 1.0:
                result_lines.append(line)

    return "\n".join(result_lines)


def add_line_numbers_to_content(content: str) -> str:
    """
    Add simple integer line numbers to content (for non-wrapped content).
    Format: "LINE_NUM: content"
    """
    lines = content.split("\n")
    numbered_lines = []

    for line_num, line in enumerate(lines, start=1):
        numbered_lines.append(f"{line_num}: {line}")

    return "\n".join(numbered_lines)


def apply_output_limit(output: str, limit: int) -> str:
    """
    Apply hard character limit to output, showing bookend truncation if exceeded.

    Args:
        output: The full output string
        limit: Maximum allowed characters

    Returns:
        Truncated output with bookend preview and informative message if limit was exceeded
    """
    if len(output) <= limit:
        return output

    # Calculate stats
    total_chars = len(output)
    total_lines = output.count("\n") + 1
    excess_kb = (total_chars - limit) / 1024

    # Bookend preview: show head + tail with middle omitted
    marker = f"\n\n[...{excess_kb:.1f} KB OMITTED...]\n\n"

    if limit >= 100 + len(marker):
        # Split limit between head and tail
        remaining = limit - len(marker)
        head_chars = remaining // 2
        tail_chars = remaining - head_chars
        preview = output[:head_chars] + marker + output[-tail_chars:]
    else:
        # Not enough room for bookends, just show head
        preview = output[:limit]

    # Compact message with actionable advice
    message = f"""
[OUTPUT TRUNCATED: {total_chars:,} chars ({total_lines} lines) exceeds --limit {limit:,} by {excess_kb:.1f} KB]
Reduce output: --shape WIDTH:HEIGHT (e.g., 120:50) or --range START:END (e.g., 1:100)
Raise limit:   --limit {total_chars} or save to file: uv run nub ... > output.txt
"""

    return preview + message


def format_with_line_numbers(lines: list[OutputLine]) -> str:
    """Format output lines with line numbers (source or sequential)."""
    result = []
    for i, line in enumerate(lines, start=1):
        # Use source line number if available, otherwise sequential
        line_num = line.source_line if line.source_line is not None else i
        result.append(f"{line_num}: {line.content}")
    return "\n".join(result)


def get_strategy(
    content: str,
    filename: str | None,
    force_type: str | None,
) -> FormatStrategy:
    """Get format strategy via override, detection, or fallback to text."""
    if force_type:
        strategy = registry.get_by_name(force_type)
        if strategy:
            return strategy
        strategy = registry.get_by_extension(force_type)
        if strategy:
            return strategy

    match = registry.detect(content, filename)
    if match:
        return match.strategy

    fallback = registry.get_by_name("text")
    if fallback:
        return fallback

    raise RuntimeError("No format strategy available")


def compress(
    content: str,
    filename: str | None = None,
    width: int = 120,
    height: int = 100,
    grep_pattern: str | None = None,
    format_type: str | None = None,
    separator: str | None = None,
    separator_regex: str | None = None,
    return_structured: bool = False,
) -> str | list[OutputLine]:
    """
    Compress content using geometry-based compression.

    Args:
        content: Content to compress
        filename: Optional filename for format detection
        width: Target characters per line
        height: Target number of lines
        grep_pattern: Optional regex to boost matching lines
        format_type: Force specific format strategy
        separator: Custom separator to split content (instead of newlines)
        separator_regex: Regex pattern to split content

    Returns:
        Compressed output as string
    """
    cfg = get_config()

    # Calculate budget from geometry
    target = width * height
    temperature = cfg.compression.temperature

    # Use custom separator strategy if provided
    using_custom_separator = separator or separator_regex
    if using_custom_separator:
        strategy = CustomSeparatorStrategy(
            separator=separator, separator_regex=separator_regex
        )
    else:
        strategy = get_strategy(content, filename, format_type)

    root = strategy.parse(content)

    if not root.children:
        return ""

    # CHUNK-BASED COMPRESSION: When using custom separator, each chunk = 1 output line
    if using_custom_separator:
        # Each chunk should compress to exactly 1 line of max `width` chars
        # Show `height` chunks total
        chunks = root.children  # These are the message/section chunks

        # Score and rank chunks
        scored = []
        for i, chunk in enumerate(chunks):
            topo = strategy.rank(chunk)
            # Use same scoring as compress_tree
            from .core import Weights, importance_score

            score = importance_score(
                chunk, i, len(chunks), topo, grep_pattern, Weights()
            )
            scored.append((chunk, score))

        # Sort by score (highest first) and take top `height` chunks
        scored.sort(key=lambda x: x[1], reverse=True)
        selected_chunks = scored[:height]

        # Sort selected chunks back to original order
        chunk_to_idx = {id(c): i for i, c in enumerate(chunks)}
        selected_chunks.sort(key=lambda x: chunk_to_idx[id(x[0])])

        # Compress each chunk to 1 line of max `width` chars
        output_lines = []
        for chunk, _score in selected_chunks:
            # Flatten chunk to single line (replace newlines with spaces)
            flattened = " ".join(
                line.strip()
                for line in chunk.content.strip().split("\n")
                if line.strip()
            )
            # Compress to fit in `width` chars
            from .core import truncate_content

            compressed = truncate_content(flattened, width)
            output_lines.append(compressed)

        return "\n".join(output_lines)

    # STANDARD LINE-BASED COMPRESSION: Original behavior
    # Reserve newlines based on expected OUTPUT lines (height), not input lines
    # Output will have at most `height` lines, so at most `height-1` newlines
    newline_reserve = max(0, height - 1)
    content_budget = max(1, target - newline_reserve)

    output_lines = compress_tree(
        root=root,
        budget=content_budget,
        ranker=strategy.rank,
        grep_pattern=grep_pattern,
        temperature=temperature,
        renderer=strategy.render,
    )

    if return_structured:
        return output_lines
    return "\n".join(line.content for line in output_lines)


def main(args: list[str] | None = None) -> int:
    """Main entry point."""
    parsed = parse_args(args)

    # Handle --profile mode
    if parsed.profile:
        if not parsed.file:
            print("Error: --profile requires a file path (not stdin)", file=sys.stderr)
            return 1

        from .profiler import format_profile_report, profile_file

        try:
            profile = profile_file(parsed.file)
            report = format_profile_report(profile)

            # Apply limit to profile output too
            if parsed.limit > 0:
                report = apply_output_limit(report, parsed.limit)

            print(report)
            return 0
        except Exception as e:
            print(f"Error profiling file: {e}", file=sys.stderr)
            return 1

    # Read content
    try:
        content, filename, is_directory = read_input(parsed.file)
    except FileNotFoundError:
        print(f"Error: File not found: {parsed.file}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error reading input: {e}", file=sys.stderr)
        return 1

    # Handle directory input specially
    if is_directory:
        assert filename is not None  # Directories always come from file path, not stdin

        # Parse shape
        try:
            width, height = parse_shape(parsed.shape)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        # Parse range if specified
        try:
            start_range, end_range = parse_range(parsed.range)
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

        # Use folder strategy directly
        folder_strategy = FolderStrategy()
        try:
            root = folder_strategy.parse_path(filename)
        except Exception as e:
            print(f"Error parsing directory: {e}", file=sys.stderr)
            return 1

        # Compress the directory tree
        # Use width * height as total budget to guide compression
        cfg = get_config()
        target = width * height
        output_lines = compress_tree(
            root=root,
            budget=target,
            ranker=folder_strategy.rank,
            grep_pattern=parsed.grep,
            temperature=cfg.compression.temperature,
            renderer=folder_strategy.render,
        )

        # Limit to height lines (shape constraint)
        if len(output_lines) > height:
            output_lines = output_lines[:height]

        # Apply range selection if specified
        if start_range is not None or end_range is not None:
            # Simple integer range for folder output (1-indexed like line numbers)
            start_idx = int(start_range) - 1 if start_range and start_range > 0 else 0
            end_idx = int(end_range) if end_range and end_range > 0 else len(output_lines)
            output_lines = output_lines[start_idx:end_idx]

        # Extract content strings for dedup and output
        content_lines = [line.content for line in output_lines]

        # Apply n-gram deduplication if enabled
        if parsed.deduplicate or cfg.compression.deduplicate_ngrams:
            content_lines = deduplicate_3grams(content_lines)

        output = "\n".join(content_lines)

        # Apply output limit
        if parsed.limit > 0:
            output = apply_output_limit(output, parsed.limit)

        print(output)
        return 0

    if not content:
        return 0

    # Parse shape
    try:
        width, height = parse_shape(parsed.shape)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Step 1: Apply wrapping (if requested) with line numbering
    # This creates fractional addresses like "1.00: text", "1.25: more"
    # SKIP if using separator mode (line numbers added after compression)
    # SKIP for structured formats (Python, JSON) - line numbers break AST parsing
    using_separator = parsed.separator or parsed.separator_regex

    # Detect if this is a structured format that needs raw content for parsing
    is_structured_format = False
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        # Structured formats that need raw content (AST-based parsing)
        is_structured_format = ext in ("py", "pyw", "json", "yaml", "yml", "toml")

    if not is_structured_format:
        if parsed.wrap and not using_separator:
            content = wrap_content(content, parsed.wrap, add_line_nums=parsed.line_numbers)
        elif parsed.line_numbers and not using_separator:
            # No wrapping, but add simple line numbers
            content = add_line_numbers_to_content(content)

    # Step 2: Apply range selection (works with fractional addresses)
    try:
        start_range, end_range = parse_range(parsed.range)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if start_range is not None and end_range is not None:
        if (parsed.wrap or parsed.line_numbers) and not using_separator and not is_structured_format:
            # Content has address prefixes, use fractional range extraction
            content = extract_fractional_range(content, start_range, end_range)
        else:
            # No prefixes, treat as integer line numbers
            # Convert fractional to integer for this case
            start_int = int(start_range)
            end_int = int(end_range)
            lines = content.split("\n")
            if start_int < 1 or start_int > len(lines):
                print(f"Error: Start line {start_int} out of range", file=sys.stderr)
                return 1
            end_int = min(end_int, len(lines))
            content = "\n".join(lines[start_int - 1 : end_int])

    if not content:
        print("Error: No content after range selection", file=sys.stderr)
        return 1

    # Step 3: Compress with geometry-based parameters
    # Handle legacy --target if specified
    if parsed.target:
        # Legacy mode: use target to derive shape
        target_budget = parsed.target
        # Estimate: assume balanced shape
        import math

        side = int(math.sqrt(target_budget))
        width = side
        height = side

    # For structured formats with line numbers, get OutputLine list for source lines
    use_source_lines = is_structured_format and parsed.line_numbers

    result = compress(
        content=content,
        filename=filename,
        width=width,
        height=height,
        grep_pattern=parsed.grep,
        format_type=parsed.format_type,
        separator=parsed.separator,
        separator_regex=parsed.separator_regex,
        return_structured=use_source_lines,
    )

    # Apply n-gram deduplication if enabled
    cfg = get_config()
    if isinstance(result, list):
        # OutputLine list - dedup content, preserve source_line
        content_lines = [line.content for line in result]
        if parsed.deduplicate or cfg.compression.deduplicate_ngrams:
            content_lines = deduplicate_3grams(content_lines)
            # Rebuild OutputLine list with deduped content
            result = [OutputLine(content=c, source_line=r.source_line)
                      for c, r in zip(content_lines, result, strict=False)]
        # Format with source line numbers
        output = format_with_line_numbers(result)
    else:
        output = result
        if parsed.deduplicate or cfg.compression.deduplicate_ngrams:
            lines = output.split("\n")
            lines = deduplicate_3grams(lines)
            output = "\n".join(lines)

        # Add sequential line numbers for separator mode (no source lines available)
        if using_separator and parsed.line_numbers:
            lines = output.split("\n")
            output = "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))

    # Apply output limit (unless disabled with --limit 0)
    if parsed.limit > 0:
        output = apply_output_limit(output, parsed.limit)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
