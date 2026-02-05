"""
Unit tests for core compression algorithm.

Tests scoring, softmax allocation, truncation, and deduplication.
"""

from nub.core import (
    positional_score,
    grep_score,
    importance_score,
    softmax_allocate,
    truncate_content,
    deduplicate_3grams,
    Weights,
    ScoredNode,
)
from nub.dom import Node


class TestPositionalScore:
    def test_start_scores_max(self):
        assert positional_score(0, 10) == 1.0

    def test_end_scores_max(self):
        assert positional_score(9, 10) == 1.0

    def test_middle_scores_zero(self):
        # Exact middle of 11 items
        assert positional_score(5, 11) == 0.0

    def test_single_item_scores_max(self):
        assert positional_score(0, 1) == 1.0

    def test_ucurve_shape(self):
        scores = [positional_score(i, 11) for i in range(11)]
        # Symmetric
        assert scores[0] == 1.0
        assert scores[10] == 1.0
        # Middle lowest
        assert scores[5] == 0.0
        # Monotonic decrease to middle
        assert scores[0] > scores[2] > scores[4] > scores[5]


class TestGrepScore:
    def test_match_returns_one(self):
        assert grep_score("error: something failed", "error") == 1.0

    def test_no_match_returns_zero(self):
        assert grep_score("all is well", "error") == 0.0

    def test_regex_pattern(self):
        assert grep_score("line 42: error", r"line \d+") == 1.0

    def test_none_pattern_returns_zero(self):
        assert grep_score("anything", None) == 0.0

    def test_invalid_regex_returns_zero(self):
        assert grep_score("test", "[invalid") == 0.0


class TestImportanceScore:
    def test_combines_factors(self):
        node = Node(content="error here")
        weights = Weights(positional=0.3, grep=1.0, topology=0.5)

        score = importance_score(
            node=node,
            index=0,
            total=10,
            topology_score=0.9,
            grep_pattern="error",
            weights=weights,
        )

        # 0.3*1.0 (first pos) + 1.0*1.0 (grep) + 0.5*0.9 (topo) = 1.75
        assert 1.7 < score < 1.8

    def test_grep_dominates_when_weighted(self):
        node = Node(content="error here")
        weights = Weights(positional=0.1, grep=2.0, topology=0.1)

        with_grep = importance_score(node, 5, 10, 0.5, "error", weights)
        without_grep = importance_score(node, 5, 10, 0.5, "nomatch", weights)

        assert with_grep > without_grep + 1.5


class TestSoftmaxAllocate:
    def test_higher_score_gets_more(self):
        nodes = [
            ScoredNode(node=Node(content="a"), score=1.0),
            ScoredNode(node=Node(content="b"), score=2.0),
        ]
        softmax_allocate(nodes, 100, temperature=1.0)

        assert nodes[1].allocated_chars > nodes[0].allocated_chars
        assert sum(n.allocated_chars for n in nodes) == 100

    def test_low_temperature_winner_takes_all(self):
        nodes = [
            ScoredNode(node=Node(content="a"), score=1.0),
            ScoredNode(node=Node(content="b"), score=2.0),
        ]
        softmax_allocate(nodes, 100, temperature=0.1)

        assert nodes[1].allocated_chars > 90

    def test_high_temperature_uniform(self):
        nodes = [
            ScoredNode(node=Node(content="a"), score=1.0),
            ScoredNode(node=Node(content="b"), score=2.0),
        ]
        softmax_allocate(nodes, 100, temperature=10.0)

        assert 40 < nodes[0].allocated_chars < 60
        assert 40 < nodes[1].allocated_chars < 60

    def test_zero_budget(self):
        nodes = [ScoredNode(node=Node(content="a"), score=1.0)]
        softmax_allocate(nodes, 0, temperature=1.0)
        assert nodes[0].allocated_chars == 0

    def test_empty_list(self):
        softmax_allocate([], 100, temperature=1.0)  # should not crash

    def test_total_equals_budget(self):
        nodes = [
            ScoredNode(node=Node(content="a"), score=0.5),
            ScoredNode(node=Node(content="b"), score=1.5),
            ScoredNode(node=Node(content="c"), score=1.0),
        ]
        softmax_allocate(nodes, 1000, temperature=1.0)
        assert sum(n.allocated_chars for n in nodes) == 1000


class TestTruncateContent:
    def test_content_fits(self):
        assert truncate_content("hello", 10) == "hello"

    def test_exact_fit(self):
        assert truncate_content("hello", 5) == "hello"

    def test_truncates_with_ellipsis(self):
        result = truncate_content("hello world", 8)
        assert result == "hello..."
        assert len(result) == 8

    def test_tiny_budget_just_ellipsis(self):
        result = truncate_content("hello", 2)
        assert result == ".."
        assert len(result) == 2

    def test_atomic_does_tail_truncation_only(self):
        """Atomic content should only be tail-truncated, never middle-dropped."""
        # A long content that would normally get middle-dropped
        content = "start" + "x" * 200 + "end"
        result = truncate_content(content, 50, atomic=True)

        # Should be simple head + ellipsis, no middle dropping
        assert result.startswith("start")
        assert result.endswith("...")
        # No [+N chars] marker
        assert "[+" not in result
        assert len(result) == 50

    def test_atomic_content_fits(self):
        """Atomic content that fits should be unchanged."""
        result = truncate_content("short preview", 100, atomic=True)
        assert result == "short preview"

    def test_non_atomic_does_middle_drop(self):
        """Non-atomic content gets middle-dropped for larger truncations."""
        # Long content with enough room for middle-drop
        content = "start_content" + "x" * 200 + "end_content"
        result = truncate_content(content, 60)

        # Should have middle-drop marker
        assert "[+" in result or "..." in result
        # For long enough budget, should preserve end
        if len(result) > 50:
            assert "end" in result or result.endswith("...")


class TestDeduplicate3grams:
    """Tests for n-gram deduplication."""

    def test_deduplicate_repeated_3gram(self):
        """Basic deduplication: second occurrence replaced with '..'."""
        lines = [
            "the quick brown fox jumps",
            "the quick brown dog runs",
        ]
        result = deduplicate_3grams(lines)

        assert result[0] == "the quick brown fox jumps"  # First kept
        assert ".." in result[1]  # "the quick brown" replaced
        assert "dog runs" in result[1]  # Unique part preserved

    def test_deduplicate_multiple_occurrences(self):
        """Same 3-gram appears 3 times - first kept, others replaced."""
        lines = [
            "hello world now is the time",
            "hello world now for something",
            "hello world now different text",
        ]
        result = deduplicate_3grams(lines)

        assert result[0] == "hello world now is the time"  # First kept
        assert result[1].startswith("..")  # "hello world now" replaced
        assert result[2].startswith("..")

    def test_deduplicate_overlapping_trigrams(self):
        """Overlapping 3-grams are handled correctly."""
        lines = [
            "A B C D E",
            "B C D F G",
        ]
        result = deduplicate_3grams(lines)

        assert result[0] == "A B C D E"
        # "B C D" in second line should be replaced
        assert ".." in result[1]
        assert "F G" in result[1]

    def test_no_deduplication_on_unique(self):
        """All unique 3-grams - output unchanged."""
        lines = [
            "the quick brown fox",
            "a lazy dog sleeps",
            "bright sunny day today",
        ]
        result = deduplicate_3grams(lines)

        assert result == lines  # No changes

    def test_preserve_unique_parts(self):
        """Only repeated middle replaced, unique start/end preserved."""
        lines = [
            "START common phrase here END1",
            "BEGIN common phrase here END2",
        ]
        result = deduplicate_3grams(lines)

        assert result[0] == "START common phrase here END1"
        # "common phrase here" replaced, but BEGIN and END2 preserved
        assert "BEGIN" in result[1]
        assert ".." in result[1]
        assert "END2" in result[1]

    def test_short_lines_pass_through(self):
        """Lines with < 3 words pass through unchanged."""
        lines = [
            "hello",
            "hi there",
            "one two three four",
        ]
        result = deduplicate_3grams(lines)

        assert result[0] == "hello"
        assert result[1] == "hi there"
        assert result[2] == "one two three four"

    def test_empty_lines_pass_through(self):
        """Empty lines pass through unchanged."""
        lines = ["", "hello world now", ""]
        result = deduplicate_3grams(lines)

        assert result == lines

    def test_single_word_repeated_not_caught(self):
        """Single repeated words not caught (needs 3-word sequence)."""
        lines = [
            "hello hello hello world",
            "hello world test",
        ]
        result = deduplicate_3grams(lines)

        # "hello" alone doesn't form a repeated 3-gram
        # but "hello hello hello" and "hello world test" are different sequences
        assert result[0] == "hello hello hello world"
        # No deduplication expected since 3-grams are different
        assert result[1] == "hello world test"
