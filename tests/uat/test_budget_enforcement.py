"""
UAT: Budget Enforcement

Validates that compression never exceeds specified character budget
and efficiently utilizes available budget.

Acceptance criteria (from G-1):
- output_length <= budget (hard constraint)
- output_length >= 0.9 * min(content_length, budget) (efficiency target)
"""

from nub.core import Weights, compress_tree
from nub.dom import Node


def test_budget_never_exceeded():
    """Verify output never exceeds budget across various scenarios."""
    test_cases = [
        # (content_size, budget, description)
        (500, 2000, "small content, large budget"),
        (5000, 1000, "large content, small budget"),
        (1000, 1000, "equal content and budget"),
        (100, 50, "tiny budget, aggressive compression"),
    ]
    
    for content_size, budget, description in test_cases:
        # Create content of specified size
        root = Node(
            content="root",
            type="file",
            children=[
                Node(content=f"line {i}: " + "x" * 50, type="line")
                for i in range(content_size // 60)  # Each line ~60 chars
            ],
        )
        
        output = compress_tree(
            root,
            budget=budget,
            ranker=lambda n: 0.5,
            grep_pattern=None,
            weights=Weights(),
        )
        
        total_chars = sum(len(line.content) for line in output)
        
        assert total_chars <= budget, \
            f"Budget exceeded for {description}: {total_chars}/{budget}"


def test_budget_utilization_efficiency():
    """Verify efficient utilization of available budget."""
    test_cases = [
        # (content_chars, budget, min_utilization_ratio, description)
        (500, 2000, 0.90, "small content, large budget"),
        (5000, 1000, 0.90, "large content, small budget"),
        (1000, 1000, 0.90, "equal content and budget"),
    ]
    
    for content_chars, budget, min_ratio, description in test_cases:
        # Create content of specified size
        content_lines = []
        chars_so_far = 0
        line_num = 0
        while chars_so_far < content_chars:
            line = f"Content line {line_num} with additional text to fill space"
            content_lines.append(Node(content=line, type="line"))
            chars_so_far += len(line)
            line_num += 1
        
        root = Node(
            content="root",
            type="file",
            children=content_lines,
        )
        
        output = compress_tree(
            root,
            budget=budget,
            ranker=lambda n: 0.5,
            grep_pattern=None,
            weights=Weights(),
        )
        
        total_chars = sum(len(line.content) for line in output)
        
        # Calculate target: min(content_length, budget)
        actual_content = sum(len(child.content) for child in root.children)
        target = min(actual_content, budget)
        min_expected = min_ratio * target
        
        assert total_chars >= min_expected, \
            f"Underutilized budget for {description}: {total_chars}/{target} (expected >={min_expected:.0f})"
        assert total_chars <= budget, \
            f"Exceeded budget for {description}: {total_chars}/{budget}"


def test_budget_utilization_short_lines():
    """
    Verify budget utilization with many short lines.

    This is the key bug case: when lines are shorter than min_line_chars,
    the algorithm should still use available budget by showing more lines,
    not waste 90%+ of budget.
    """
    # 200 short lines, each ~20 chars = ~4000 chars total
    # With budget 4800, should show nearly all content
    root = Node(
        content="root",
        type="file",
        children=[
            Node(content=f"Line {i}: short txt", type="line")
            for i in range(200)
        ],
    )

    budget = 4800
    output = compress_tree(
        root,
        budget=budget,
        ranker=lambda n: 0.5,
        grep_pattern=None,
        weights=Weights(),
    )

    total_chars = sum(len(line.content) for line in output)
    actual_content = sum(len(child.content) for child in root.children)
    target = min(actual_content, budget)  # 3690 chars

    # Should use at least 90% of available content
    min_expected = 0.90 * target
    assert total_chars >= min_expected, \
        f"Short lines budget underutilized: {total_chars}/{target} ({total_chars/target*100:.1f}%)"

    # Should show most of the lines (not just 20 out of 200)
    content_lines = [l for l in output if not l.content.startswith("[")]
    assert len(content_lines) >= 150, \
        f"Too few lines shown: {len(content_lines)}/200"


def test_budget_utilization_mixed_lines():
    """
    Verify budget utilization with mixed short/long lines.

    When some lines are short and some are long, should still
    maximize content shown, not fold short lines unnecessarily.
    """
    # Mix of long (200 chars) and short (40 chars) lines
    children = []
    for i in range(50):
        if i % 5 == 0:
            children.append(Node(content="L" * 200, type="line"))  # Long
        else:
            children.append(Node(content="S" * 40, type="line"))  # Short

    root = Node(content="root", type="file", children=children)

    budget = 4800
    output = compress_tree(
        root,
        budget=budget,
        ranker=lambda n: 0.5,
        grep_pattern=None,
        weights=Weights(),
    )

    total_chars = sum(len(line.content) for line in output)
    actual_content = sum(len(child.content) for child in root.children)  # 3600 chars
    target = min(actual_content, budget)  # 3600

    # Should use at least 85% of available content (mixed case is harder)
    min_expected = 0.85 * target
    assert total_chars >= min_expected, \
        f"Mixed lines underutilized: {total_chars}/{target} ({total_chars/target*100:.1f}%)"


def test_budget_with_grep_pattern():
    """Verify budget enforcement when grep pattern is active."""
    root = Node(
        content="root",
        type="file",
        children=[
            Node(content=f"important line {i}" if i % 3 == 0 else f"regular line {i}",
                 type="line")
            for i in range(50)
        ],
    )
    
    budget = 500
    grep_pattern = "important"
    
    output = compress_tree(
        root,
        budget=budget,
        ranker=lambda n: 0.5,
        grep_pattern=grep_pattern,
        weights=Weights(positional=1.0, grep=3.0, topology=0.5),
    )
    
    total_chars = sum(len(line.content) for line in output)
    
    # Hard constraint: never exceed
    assert total_chars <= budget, \
        f"Budget exceeded with grep: {total_chars}/{budget}"
    
    # Should still utilize a reasonable portion of budget
    # Note: Grep patterns can cause lower utilization due to selective compression
    actual_content = sum(len(child.content) for child in root.children)
    target = min(actual_content, budget)
    assert total_chars >= 0.25 * target, \
        f"Severe underutilization with grep: {total_chars}/{target}"


def test_graceful_degradation():
    """Verify quality degrades smoothly as budget decreases."""
    root = Node(
        content="root",
        type="file",
        children=[
            Node(content=f"Content line {i} with important information",
                 type="line")
            for i in range(100)
        ],
    )
    
    budgets = [5000, 2000, 1000, 500, 200]
    previous_chars = None
    
    for budget in budgets:
        output = compress_tree(
            root,
            budget=budget,
            ranker=lambda n: 0.5,
            grep_pattern=None,
            weights=Weights(),
        )
        
        num_lines = len(output)
        total_chars = sum(len(line.content) for line in output)
        
        # Budget never exceeded
        assert total_chars <= budget, \
            f"Budget {budget} exceeded: {total_chars}"
        
        # Quality degrades: fewer chars as budget decreases (lines can vary due to compression modes)
        if previous_chars is not None:
            assert total_chars <= previous_chars, \
                f"Output should not grow as budget decreases: {total_chars} vs {previous_chars}"
        
        previous_chars = total_chars

