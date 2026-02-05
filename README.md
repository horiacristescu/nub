# Nub

**Semantic compression for AI agents. Any content, any size, fit to a budget.**

Agents have to work through large, messy artifacts: entire repositories, long logs, chat sessions, and sprawling codebases. But their context windows are limited. Chunking for retrieval breaks structure. Head-and-tail summaries strip away meaning. What's left is often fragments without a sense of how they fit together.

Nub approaches the problem differently. It compresses any content to a fixed character budget while keeping the structure that actually matters. Code retains its function signatures, folders still show meaningful previews, and markdown keeps its headings. An agent can skim at 100:1 to get oriented, then zoom to full detail where needed. It works less like a summary and more like a map — Google Maps, but for text.

## Install

```bash
pip install .
```

Requires Python 3.11+. Zero runtime dependencies.

## Quick start

Compress a Python file (604 lines down to a structural overview):

```
$ nub src/nub/core.py -s 80:8
1: [8 imports, lines 10-19]
23: OutputLine
48: ScoredNode
56: positional_score
64: grep_score
85: importance_score
109: softmax_allocate
150: truncate_content
206: calculate_line_budget
235: select_lines_by_ucurve
298: _merge_fold_markers
347: _enforce_budget
386: compress_tree
545: deduplicate_3grams
```

The `--shape` flag controls the output geometry: `80:8` means 80 characters wide, 8 lines tall. The budget is `width * height` characters.

## How it works

Nub parses content into a tree, scores each node by position, topology, and optional grep relevance, then allocates the character budget proportionally using softmax. As budget shrinks, detail degrades gracefully through four levels:

- **Focus** (1:1) — full source, nothing removed
- **Detailed** (2:1) — signatures with body sketches
- **Regional** (10:1) — signatures and docstrings
- **Overview** (100:1) — names only, then fold markers

Structure is always preserved. Budget pressure falls on implementation details, not on the scaffolding that tells you where you are.

## Examples

**Browse a folder** — each file gets a content preview and size:

```
$ nub src/nub/ -s 70:12
nub/
  formats/
    base.py - """ Base format ...
    folder.py - ...
    markdown.py - "...
    python.py - """ Python AST...
    text.py - """ Text format str...
  cli.py - """ CLI interface for Nub. Pipe-friendly compression...
  core.py - """ Core compression algorithm for Nub. Implements...
  dom.py - """ DOM - Document Object Model for Nub... [2.3 KB]
  profiler.py - """ File profiler - detect state features... [13.7 KB]
```

**Grep boost** — matching lines float to the top of the budget:

```
$ nub src/nub/core.py -s 60:6 -g "def compress"
1: [8 imports, lines 1...
386: compress_tree
545: deduplicate_3grams
298: _merge_fold_markers
347: _enforce_budget
150: truncate_content
```

**Zoom into a region** — drill from overview to full source:

```
$ nub src/nub/core.py -r 386:400 -N
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
```

**Markdown** — heading hierarchy preserved at any budget:

```
$ nub MIND_MAP.md -s 60:8 -N
# Nub - Smart Context Compression
[1] **Project Overview** - Semantic zoom...
[2] **Core Algorithm** - Parse → Score...
[3] **Content Detection** - Decentrali...
[4] **Level of Detail (LOD)** - Zoom-l...
[5] **CLI** - `nub [file|directory]...
[6] **Agent Workflow** - Multi-resol...
[...13 more...]
```

## The agent workflow

Nub is designed for multi-step exploration. Each call is stateless — the agent's conversation history provides continuity.

```
nub project/          -s 30:400    # 1. Tall index: scan the file tree
nub project/          -g "auth"    # 2. Grep: find where auth lives
nub project/src/auth/ -s 80:20     # 3. Zoom: overview of the auth module
nub project/src/auth/login.py      # 4. Focus: read the file that matters
nub project/src/auth/login.py -r 50:80  # 5. Drill: specific line range
```

The shape flag gives you different "cuts" of the same content. Wide and short (`120:30`) for code overviews. Tall and narrow (`30:400`) for scanning file trees. The content adapts.

## CLI reference

```
nub [file|directory] [options]

--shape, -s W:H     Output shape as WIDTH:HEIGHT (default: 120:100)
--range, -r S:E     Line range (supports fractional: 1.0:5.50)
--grep, -g PATTERN  Boost lines matching regex
--wrap, -w WIDTH    Wrap long lines with fractional addresses
--deduplicate, -d   Remove repeated 3-grams across output
--profile, -p       Analyze file features and recommend strategy
--type FORMAT       Force format (text, python, markdown, folder, mindmap)
--no-line-numbers   Disable source line numbers
--limit N           Max output chars (default: 10000)
```

Reads from stdin if no file is given, so it composes with pipes.

## Format strategies

Nub detects content type and applies format-specific compression:

| Format | Detection | What it preserves |
|--------|-----------|-------------------|
| Python | `.py` extension | AST structure: classes, functions, signatures, decorators |
| Markdown | `.md` extension | Heading hierarchy (H1 > H2 > H3), code blocks |
| Folder | Directory path | File tree with content previews and sizes |
| MindMap | `[N]` node syntax | Node references ranked by connectivity |
| Text | Fallback | Section boundaries, positional U-curve (start/end priority) |

## Status

Working and tested (2,800 LOC, 183 tests), but still evolving.

- [x] Python (AST-aware: classes, functions, signatures, decorators)
- [x] Markdown (heading hierarchy, code blocks)
- [x] Folder (file tree with content previews)
- [x] MindMap (node references ranked by connectivity)
- [x] Plain text (section boundaries, U-curve sampling)
- [x] Large file handling (head+tail for >1MB files)
- [x] N-gram deduplication (cross-document 3-gram unicity)
- [x] File profiler (`--profile` for strategy recommendations)
- [ ] JSON (schema + sample values at each depth level)
- [ ] CSV (header-anchored row sampling)
- [ ] Conversation logs (.jsonl with role priority)
- [ ] Archives (.zip as virtual filesystem)
- [ ] PDF extraction
- [ ] Semantic similarity (`--semantic` for embedding-based boosting)

Contributions welcome. This is a work in progress.

## License

MIT
