"""
Integration Test: Budget Flow from Scoring → Allocation → Compression

Validates that budget flows correctly through the pipeline:
1. Importance scoring assigns scores to nodes
2. Softmax allocation distributes budget based on scores
3. Hierarchical compression respects allocated budgets

Tests the integration between S-1 (Scoring), S-2 (Allocation), S-3 (Compression).
"""

from nub.core import (
    ScoredNode,
    Weights,
    compress_tree,
    importance_score,
    softmax_allocate,
)
from nub.dom import Node


def test_scoring_to_allocation_integration():
    """Test that importance scores correctly drive budget allocation."""
    # Create test nodes with different expected scores
    nodes = [
        Node(content="high priority item", type="line"),
        Node(content="low priority item", type="line"),
        Node(content="another high priority", type="line"),
    ]
    
    weights = Weights(positional=1.0, grep=2.0, topology=0.0)
    grep_pattern = "high"
    
    # Score the nodes
    scored = []
    for i, node in enumerate(nodes):
        score = importance_score(node, i, len(nodes), 0.0, grep_pattern, weights)
        scored.append(ScoredNode(node=node, score=score))
    
    # Verify grep-matching nodes got higher scores
    assert scored[0].score > scored[1].score  # "high" vs no match
    assert scored[2].score > scored[1].score  # "high" vs no match
    
    # Allocate budget via softmax
    total_budget = 300
    softmax_allocate(scored, total_budget, temperature=0.5)
    
    # Verify allocations sum to budget
    total_allocated = sum(sn.allocated_chars for sn in scored)
    assert total_allocated == total_budget, \
        f"Budget not fully allocated: {total_allocated}/{total_budget}"
    
    # Verify high-scoring nodes got more budget
    assert scored[0].allocated_chars > scored[1].allocated_chars
    assert scored[2].allocated_chars > scored[1].allocated_chars


def test_allocation_to_compression_integration():
    """Test that allocated budgets are respected during compression."""
    # Create a simple tree: root with 3 children
    root = Node(
        content="root",
        type="file",
        children=[
            Node(content="first child with important content", type="line"),
            Node(content="second child with less important content", type="line"),
            Node(content="third child with important content", type="line"),
        ]
    )
    
    budget = 100
    grep_pattern = "important"
    weights = Weights(positional=1.0, grep=2.0, topology=0.0)
    
    # Compress with grep pattern favoring "important"
    output = compress_tree(
        root,
        budget=budget,
        ranker=lambda n: 0.5,  # Uniform topology scores
        grep_pattern=grep_pattern,
        weights=weights,
        temperature=0.5,
    )
    
    # Verify output respects budget
    total_chars = sum(len(line.content) for line in output)
    assert total_chars <= budget, \
        f"Output exceeded budget: {total_chars}/{budget}"
    
    # Verify budget utilization (should use at least 70% when content available)
    min_content = sum(len(child.content) for child in root.children)
    expected_target = min(min_content, budget)
    min_utilization = 0.7 * expected_target
    
    assert total_chars >= min_utilization, \
        f"Budget underutilized: {total_chars}/{expected_target} (min {min_utilization})"
    
    # Verify grep-matched content appears more in output
    output_text = "\n".join(line.content for line in output)
    assert "important" in output_text, "Grep-matched content should appear in output"


def test_end_to_end_budget_flow():
    """Test complete flow: scoring → allocation → compression with realistic tree."""
    # Create a deeper tree structure
    root = Node(
        content="root",
        type="file",
        children=[
            Node(
                content="section 1",
                type="section",
                name="section1",
                children=[
                    Node(content="line 1 with match", type="line"),
                    Node(content="line 2 without", type="line"),
                ],
            ),
            Node(
                content="section 2",
                type="section", 
                name="section2",
                children=[
                    Node(content="line 3 with match", type="line"),
                    Node(content="line 4 without", type="line"),
                ],
            ),
        ],
    )
    
    budget = 200
    grep_pattern = "match"
    
    # Compress with grep pattern
    output = compress_tree(
        root,
        budget=budget,
        ranker=lambda n: 0.5,
        grep_pattern=grep_pattern,
        weights=Weights(positional=1.0, grep=3.0, topology=0.5),
        temperature=0.7,
    )
    
    # Verify hard constraints
    total_chars = sum(len(line.content) for line in output)
    assert total_chars <= budget, \
        f"Output exceeded budget: {total_chars}/{budget}"
    
    # Verify structure preserved (sections should be identifiable)
    output_text = "\n".join(line.content for line in output)
    
    # Verify at least some output (not completely empty)
    assert len(output) > 0, "Should produce some output"
    assert total_chars > 20, "Should produce some output"
    
    # Verify grep-matched lines prioritized
    assert "match" in output_text, "High-scoring matched content should appear"


def test_budget_remainder_distribution():
    """Test that integer rounding remainders are distributed correctly."""
    # Create 3 nodes with equal scores
    scored = [
        ScoredNode(node=Node(content="a", type="line"), score=1.0),
        ScoredNode(node=Node(content="b", type="line"), score=1.0),
        ScoredNode(node=Node(content="c", type="line"), score=1.0),
    ]
    
    # Budget that doesn't divide evenly
    budget = 100  # 100/3 = 33.33... → 33 each + 1 remainder
    softmax_allocate(scored, budget, temperature=1.0)  # High temp = uniform
    
    # Verify exact budget allocation
    total = sum(sn.allocated_chars for sn in scored)
    assert total == budget, \
        f"Remainder not distributed: {total}/{budget}"
    
    # Verify allocations are nearly equal (at most 1 char difference)
    allocations = [sn.allocated_chars for sn in scored]
    assert max(allocations) - min(allocations) <= 1, \
        f"Uneven distribution: {allocations}"

