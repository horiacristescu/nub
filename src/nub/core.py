"""
Core compression algorithm for Nub.

Implements:
- Importance scoring: S = w_p*P + w_g*G + w_t*T
- Softmax budget allocation with temperature control
- Hierarchical tree compression with folding
"""

from __future__ import annotations

import contextlib
import math
import re
from collections.abc import Callable
from dataclasses import dataclass, field

from .config import get_config
from .dom import Node


@dataclass
class OutputLine:
    """A line of compressed output with optional source location."""
    content: str
    source_line: int | None = None


@dataclass
class Weights:
    """Importance score weights."""
    positional: float = field(default=-1.0)
    grep: float = field(default=-1.0)
    topology: float = field(default=-1.0)

    def __post_init__(self):
        # Fill from config if not specified (-1 is sentinel)
        cfg = get_config().weights
        if self.positional < 0:
            self.positional = cfg.positional
        if self.grep < 0:
            self.grep = cfg.grep
        if self.topology < 0:
            self.topology = cfg.topology


@dataclass
class ScoredNode:
    """A node with its computed importance score and budget allocation."""
    node: Node
    score: float
    allocated_chars: int = 0
    children: list[ScoredNode] = field(default_factory=list)


def positional_score(index: int, total: int) -> float:
    """U-curve: high at start/end, low in middle. Returns [0, 1]."""
    if total <= 1:
        return 1.0
    normalized = index / (total - 1)
    return (math.cos(2 * math.pi * normalized) + 1) / 2


def grep_score(content: str, pattern: str | None) -> float:
    """Returns 1.0 if content matches pattern, 0.0 otherwise."""
    if pattern is None:
        return 0.0
    try:
        if re.search(pattern, content):
            return 1.0
    except re.error:
        pass
    return 0.0


def node_contains_match(node: Node, pattern: str | None) -> bool:
    """Check if node or any descendant contains grep match."""
    if pattern is None:
        return False
    if grep_score(node.content, pattern) > 0:
        return True
    return any(node_contains_match(child, pattern) for child in node.children)


def importance_score(
    node: Node,
    index: int,
    total: int,
    topology_score: float,
    grep_pattern: str | None,
    weights: Weights,
) -> float:
    """
    Compute S = w_p*P + w_g*G + w_t*T
    For container nodes, grep checks descendants too.
    """
    p = positional_score(index, total)

    # For containers (sections), check if any child matches
    if node.children:
        g = 1.0 if node_contains_match(node, grep_pattern) else 0.0
    else:
        g = grep_score(node.content, grep_pattern)

    t = topology_score
    return weights.positional * p + weights.grep * g + weights.topology * t


def softmax_allocate(
    scored_nodes: list[ScoredNode],
    total_budget: int,
    temperature: float,
) -> None:
    """Distribute budget proportionally via softmax. Modifies in place."""
    if not scored_nodes or total_budget <= 0:
        for sn in scored_nodes:
            sn.allocated_chars = 0
        return

    scores = [sn.score for sn in scored_nodes]
    max_score = max(scores)

    if temperature <= 0:
        exp_scores = [1.0 if s == max_score else 0.0 for s in scores]
    else:
        exp_scores = [math.exp((s - max_score) / temperature) for s in scores]

    total_exp = sum(exp_scores)
    probs = [e / total_exp for e in exp_scores]

    # Allocate proportionally
    allocated = 0
    for i, sn in enumerate(scored_nodes):
        chars = int(probs[i] * total_budget)
        sn.allocated_chars = chars
        allocated += chars

    # Distribute remainder to top scorers
    remainder = total_budget - allocated
    if remainder > 0:
        sorted_indices = sorted(
            range(len(scored_nodes)),
            key=lambda i: scored_nodes[i].score,
            reverse=True
        )
        for i in range(remainder):
            scored_nodes[sorted_indices[i % len(sorted_indices)]].allocated_chars += 1


def truncate_content(
    content: str,
    max_chars: int,
    ellipsis: str = "...",
    atomic: bool = False,
) -> str:
    """
    Truncate to max_chars, adding smart ellipsis that shows bytes cut.

    For short truncations, takes the start. For longer content where we have
    room for context, removes the middle to preserve both start and end.

    If atomic=True, content is pre-optimized (e.g., file previews) and should
    only be tail-truncated, never middle-dropped.

    Smart ellipsis markers:
    - < 100 chars removed: "..."
    - >= 100 chars removed: "...[+N chars]..."
    - >= 1000 chars removed: "...[+X.X KB]..."
    """
    if len(content) <= max_chars:
        return content

    chars_removed = len(content) - max_chars

    # Atomic content: simple tail truncation only
    if atomic:
        if max_chars <= len(ellipsis):
            return ellipsis[:max_chars]
        return content[:max_chars - len(ellipsis)] + ellipsis

    # Create smart ellipsis marker
    if chars_removed < 100:
        marker = ellipsis
    elif chars_removed < 1000:
        marker = f"...[+{chars_removed} chars]..."
    else:
        kb = chars_removed / 1024
        marker = f"...[+{kb:.1f} KB]..."

    if max_chars <= len(marker):
        return marker[:max_chars]

    # If we have room for meaningful start+end (at least 20 chars each side)
    # use middle-removal, otherwise just truncate from start
    if max_chars >= 40 + len(marker):
        # Keep start and end, remove middle
        remaining = max_chars - len(marker)
        start_len = remaining // 2
        end_len = remaining - start_len
        return content[:start_len] + marker + content[-end_len:]
    else:
        # Just truncate from start for short budgets
        return content[:max_chars - len(marker)] + marker


def calculate_line_budget(num_lines: int, total_budget: int,
                          min_chars_per_line: int = 160,
                          min_lines_target: int = 20) -> int:
    """
    Calculate how many chars each line should get.

    Strategy:
    - Aim for min_chars_per_line (160) per line if possible
    - Aim for min_lines_target (20) lines minimum
    - Use full budget by extending per-line allocation when we have excess

    Examples:
        2 lines, 4000 budget → 2000 chars/line (use the budget!)
        100 lines, 4000 budget → 40 chars/line (limited by budget)
        50 lines, 10000 budget → 200 chars/line (160 min + extra)
    """
    if num_lines == 0:
        return 0

    # Calculate what we can afford
    affordable_per_line = total_budget // num_lines

    # If we have lots of budget, extend beyond minimum
    # But cap at 2x minimum to avoid showing full giant lines
    max_per_line = min_chars_per_line * 2

    return min(affordable_per_line, max_per_line)


def select_lines_by_ucurve(scored_nodes: list[ScoredNode],
                           budget: int,
                           min_chars_per_line: int = 160,
                           min_lines_target: int = 20) -> list[ScoredNode]:
    """
    Greedy selection of lines using U-curve scores.

    Algorithm:
    1. Sort by U-curve score (already in scored_nodes)
    2. Calculate how many lines we can afford
    3. Calculate chars per line (extending budget if we have few lines)
    4. Greedily select highest-scoring lines

    Returns: list of selected ScoredNode items with allocated_chars set
    """
    if not scored_nodes or budget <= 0:
        return []

    # Sort by score descending (U-curve: high at ends, low in middle)
    sorted_by_score = sorted(scored_nodes, key=lambda sn: sn.score, reverse=True)

    # How many lines can we afford at min_chars_per_line?
    max_affordable_lines = budget // min_chars_per_line

    # Target: show at least min_lines_target, but no more than we can afford
    target_lines = min(len(sorted_by_score), max(min_lines_target, max_affordable_lines))

    # Calculate chars per line for target_lines (may extend beyond minimum if budget allows)
    chars_per_line = calculate_line_budget(target_lines, budget, min_chars_per_line, min_lines_target)

    # Greedy selection
    selected = []
    remaining_budget = budget

    for i, sn in enumerate(sorted_by_score):
        if remaining_budget <= 0:
            break

        # How many chars does this line need?
        content_len = len(sn.node.content)

        # Allocate min(content_len, chars_per_line, remaining_budget)
        # This ensures we don't over-allocate to short lines
        allocated = min(content_len, chars_per_line, remaining_budget)

        # For very high-scoring lines (top 10%), relax the minimum threshold
        # This ensures we show the absolute start/end lines even if they're short
        is_high_priority = (i < len(sorted_by_score) * 0.1)  # Top 10% by score

        # min_threshold prevents showing useless truncated fragments
        # But if content_len <= threshold, the allocation IS the full content, not a fragment
        # So accept if we're showing the complete line OR if it's high priority
        is_complete_line = (allocated == content_len)
        min_threshold = 1 if (is_high_priority or is_complete_line) else 20

        if allocated >= min_threshold:
            sn.allocated_chars = allocated
            selected.append(sn)
            remaining_budget -= allocated

    return selected


def _merge_fold_markers(lines: list[OutputLine]) -> list[OutputLine]:
    """Merge consecutive fold markers ([...N more...] and [N items, budget too low])."""
    if not lines:
        return lines

    result: list[OutputLine] = []
    pending_count = 0

    for line in lines:
        # Check if this is a fold marker (either type)
        count = None
        content = line.content
        if content.startswith("[...") and content.endswith(" more...]"):
            with contextlib.suppress(ValueError, IndexError):
                count = int(content[4:content.index(" more")])
        elif content.endswith(" items, budget too low]"):
            with contextlib.suppress(ValueError, IndexError):
                count = int(content[1:content.index(" items")])

        if count is not None:
            pending_count += count
            continue

        # Flush pending fold count before adding regular line
        if pending_count > 0:
            result.append(OutputLine(content=f"[...{pending_count} more...]"))
            pending_count = 0
        result.append(line)

    # Flush trailing fold count
    if pending_count > 0:
        result.append(OutputLine(content=f"[...{pending_count} more...]"))

    # Guard against pathological case: only fold markers, no content
    non_marker_lines = [
        line for line in result
        if not (line.content.startswith("[...") and line.content.endswith(" more...]"))
    ]
    if not non_marker_lines and result:
        # If we only have markers, return a summary message instead
        total_folded = sum(
            int(line.content[4:line.content.index(" more")]) for line in result
            if line.content.startswith("[...") and " more...]" in line.content
        )
        return [OutputLine(content=f"[{total_folded} items, budget too low]")]

    return result


def _enforce_budget(lines: list[OutputLine], budget: int) -> list[OutputLine]:
    """
    Enforce budget constraint by trimming lines if total exceeds budget.

    This is a safety net for fold markers and ellipsis that can push output
    over budget. Removes lines from the end until budget is satisfied.
    """
    if not lines:
        return lines

    total_chars = sum(len(line.content) for line in lines)

    if total_chars <= budget:
        return lines

    # Budget exceeded - need to trim from the end
    result: list[OutputLine] = []
    chars_used = 0
    marker_added = False

    for line in lines:
        # Check if adding this line would exceed budget
        # Reserve space for truncation marker if needed
        marker = "...[truncated to fit budget]"
        reserve = len(marker) if not marker_added else 0

        if chars_used + len(line.content) + reserve <= budget:
            result.append(line)
            chars_used += len(line.content)
        else:
            # Can't fit more lines - add truncation marker if it fits
            if chars_used + len(marker) <= budget:
                result.append(OutputLine(content=marker))
                marker_added = True
            break

    return result


def compress_tree(
    root: Node,
    budget: int,
    ranker: Callable[[Node], float],
    grep_pattern: str | None = None,
    weights: Weights | None = None,
    temperature: float | None = None,
    min_line_chars: int | None = None,
    renderer: Callable[[Node, int], str | None] | None = None,
) -> list[OutputLine]:
    """
    Compress a tree hierarchically, returning output lines.

    Budget flows down: root -> children -> grandchildren.
    Nodes below min threshold get folded into markers.
    """
    cfg = get_config()
    if weights is None:
        weights = Weights()
    if temperature is None:
        temperature = cfg.compression.temperature
    if min_line_chars is None:
        min_line_chars = cfg.compression.min_line_chars

    # Default renderer: truncate content (no semantic degradation)
    if renderer is None:
        def default_renderer(node: Node, max_chars: int) -> str | None:
            if max_chars <= 0:
                return None
            return truncate_content(node.content, max_chars, atomic=node.atomic)
        renderer = default_renderer

    # Handle leaf node (no children)
    if not root.children:
        if budget <= 0:
            return []
        content = renderer(root, budget)
        if content is None:
            return []  # Renderer says fold this node
        return [OutputLine(content=content, source_line=root.source_line)]

    # For container nodes (like directories), output own content first
    # This ensures directory names appear in the output
    output_lines: list[OutputLine] = []
    remaining_budget = budget

    if root.content.strip():
        # Container has its own content (e.g., "dirname/") - output it
        content_len = len(root.content)
        if content_len <= remaining_budget:
            output_lines.append(OutputLine(content=root.content, source_line=root.source_line))
            remaining_budget -= content_len

    # Score children
    children = root.children

    scored = []
    for i, child in enumerate(children):
        topo = ranker(child)
        score = importance_score(child, i, len(children), topo, grep_pattern, weights)
        scored.append(ScoredNode(node=child, score=score))

    # Check if we have many items relative to budget
    # If average allocation would be below threshold, use U-curve selection
    avg_per_child = remaining_budget / len(children) if children else 0
    use_ucurve = avg_per_child < min_line_chars and len(children) > 50

    if use_ucurve:
        # Many items, low budget: select subset via U-curve
        selected = select_lines_by_ucurve(scored, remaining_budget, min_line_chars)
        # Mark unselected items as folded (allocated_chars = 0)
        selected_set = {id(sn) for sn in selected}
        for sn in scored:
            if id(sn) not in selected_set:
                sn.allocated_chars = 0
    else:
        # Softmax allocate budget to all children
        # Let the renderer decide what detail level to show (or fold if budget too small)
        softmax_allocate(scored, remaining_budget, temperature)

        # Redistribute excess budget from items that don't need their full allocation
        # This prevents waste when short content gets more budget than it needs
        # Skip container nodes (they need budget for children, not their own content)
        excess_budget = 0
        for sn in scored:
            if sn.node.children:
                continue  # Container node - needs budget for children
            content_len = len(sn.node.content)
            if sn.allocated_chars > content_len:
                excess_budget += sn.allocated_chars - content_len
                sn.allocated_chars = content_len

        # Redistribute excess to leaf items that could use more (sorted by score)
        if excess_budget > 0:
            sorted_by_score = sorted(scored, key=lambda sn: sn.score, reverse=True)
            for sn in sorted_by_score:
                if excess_budget <= 0:
                    break
                if sn.node.children:
                    continue  # Container node - skip
                content_len = len(sn.node.content)
                if sn.allocated_chars < content_len:
                    # This item could use more
                    need = content_len - sn.allocated_chars
                    give = min(need, excess_budget)
                    sn.allocated_chars += give
                    excess_budget -= give


    # Process each child - let renderer decide detail level or fold
    folded_count = 0

    for sn in scored:
        # Try to render with allocated budget
        # Renderer returns None if budget too small → fold
        if sn.node.children:
            # Container node: recurse
            child_lines = compress_tree(
                sn.node,
                sn.allocated_chars,
                ranker,
                grep_pattern,
                weights,
                temperature,
                min_line_chars,
                renderer,
            )
            if not child_lines:
                # Recursion produced nothing → fold
                folded_count += 1
                continue
        else:
            # Leaf node: use renderer for progressive LOD
            rendered = renderer(sn.node, sn.allocated_chars)
            if rendered is None:
                # Renderer says budget too small → fold
                folded_count += 1
                continue
            child_lines = [OutputLine(content=rendered, source_line=sn.node.source_line)]

        # Flush pending folded nodes before adding content
        if folded_count > 0:
            output_lines.append(OutputLine(content=f"[...{folded_count} more...]"))
            folded_count = 0

        output_lines.extend(child_lines)

    # Flush trailing folded nodes
    if folded_count > 0:
        output_lines.append(OutputLine(content=f"[...{folded_count} more...]"))

    # Merge consecutive fold markers
    merged_lines = _merge_fold_markers(output_lines)

    # CRITICAL: Enforce budget constraint
    # Fold markers and ellipsis can cause budget overrun - trim if needed
    return _enforce_budget(merged_lines, budget)


def deduplicate_3grams(lines: list[str]) -> list[str]:
    """
    Remove repeated 3-word sequences from output lines.

    Enforces a 3-gram unicity constraint - no 3-word sequence appears twice.
    Repeated sequences are replaced with ".." markers to indicate deduplication.

    Args:
        lines: List of output lines (strings)

    Returns:
        List of deduplicated lines with ".." markers
    """
    seen_3grams: set[tuple[str, str, str]] = set()
    output = []

    for line in lines:
        words = line.split()
        if len(words) < 3:
            # Not enough words to form 3-gram, pass through unchanged
            output.append(line)
            continue

        skip_flags = [False] * len(words)

        i = 0
        while i < len(words):
            if i + 2 < len(words):  # Can form 3-gram
                trigram = (words[i], words[i + 1], words[i + 2])

                if trigram in seen_3grams:
                    # Mark these 3 words for removal
                    skip_flags[i] = True
                    skip_flags[i + 1] = True
                    skip_flags[i + 2] = True
                    i += 3  # Skip past this repeated trigram
                else:
                    # New trigram - record it and move forward
                    seen_3grams.add(trigram)
                    i += 1
            else:
                # Not enough words left for 3-gram
                i += 1

        # Build output line, replacing flagged sequences with ".."
        output_words = []
        i = 0
        while i < len(words):
            if skip_flags[i]:
                # Consume all consecutive flagged words
                while i < len(words) and skip_flags[i]:
                    i += 1
                output_words.append("..")
            else:
                output_words.append(words[i])
                i += 1

        output.append(" ".join(output_words))

    return output
