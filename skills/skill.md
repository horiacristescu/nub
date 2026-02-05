---
name: nub
description: >
  Use when exploring content too large for normal tools: files >10K chars,
  folders with many files, large logs, codebases. Teaches LoD (level of detail)
  patterns for progressive navigation.
argument-hint: [file-or-folder]
---

# Nub: Level-of-Detail for Large Content

Nub compresses content while preserving structure. Think telescope for code - adjust magnification to see landscape (overview) or details (zoomed).

## When to Use Nub

**Use when normal tools fail:**
- Files >10K chars (Read truncates)
- Folders with many files (survey codebases)
- Large logs (JSONL, build output)
- Books, docs, data dumps

**Don't use when:**
- Read tool works fine (<10K)
- Need exact content
- Single small file

## Phase 0: Recon First (30 seconds)

**Before using nub**, get metrics with Unix tools:

```bash
du -h --max-depth=1 | sort -h    # Size by directory
tree -L 2                         # Structure overview
find . -type f | wc -l            # File count
ls -lhS | head -10                # 10 largest files
```

This informs nub strategy: use index mode for 1000+ files, overview for <100.

## Shape Selection

`--shape WIDTH:HEIGHT` = budget (W × H chars). **Aspect ratio determines mode.**

| Shape | Purpose | When |
|-------|---------|------|
| `120:30-40` | **Default** - balanced | Start here (validated sweet spot) |
| `30:300` | Index - scannable list | See all files in directory |
| `100:50` | Overview - structure | First look at project |
| `120:60` | Reading - comfortable | Individual files |

**For massive projects:** Start focused, not broad. Don't `nub ~/huge_project`, do `nub ~/huge_project/src/module`.

## Essential Flags

**`--deduplicate`** (or `-d`) - **Game changer for code**
- Removes repetitive imports/boilerplate
- Shows what's DIFFERENT between files
- Essential for: test dirs, code exploration
- Skip for: diverse content

**`--grep PATTERN`** - Topology booster (not just filter)
- Preserves matches under compression
- Use for: finding class definitions, imports, patterns
- Example: `--grep "class.*Strategy"`

**`--range START:END`** - Progressive navigation
- Essential for files >1MB
- Navigate large files section by section
- Example: `--range 1:50`, then `--range 50:100`

## Exploration Workflow

```bash
# 1. Recon (which dirs are large?)
du -h --max-depth=1 | sort -h

# 2. Start focused (not at root!)
nub ~/project/src --shape 120:40

# 3. Use dedup for code
nub ~/project/src --shape 120:40 -d

# 4. Find patterns
nub ~/project/src --grep "class|def" -d

# 5. Zoom into file
nub ~/project/src/module.py --shape 120:60

# 6. Navigate large file
nub large.jsonl --range 1:50 --shape 120:40
```

## Strategic Patterns

**Repository Cartography** (new codebase):
1. Docs: `nub README.md --shape 120:60`
2. Config: `nub pyproject.toml --shape 100:40`
3. Modules: `nub src/core --shape 120:40 -d`

**Code Archaeology** (find patterns):
- `nub src/ --grep "class.*Base" -d` - inheritance
- `nub tests/ --shape 100:40 -d` - test suite

**Data Exploration** (large files):
- `nub data.jsonl --range 1:30` - sample
- `nub logs/ --grep "ERROR" --range 1:50` - errors

## JSONL Exploration

Nub treats JSONL as text. Use **jq + nub pipeline** for structured exploration.

**Quick pattern:**
```bash
jq -r '"\(.time) | \(.title[0:50])"' data.jsonl > /tmp/idx.txt
nub /tmp/idx.txt --range 1:100 --shape 100:30
```

**Full guide:** See `jsonl.md` in this skill folder for:
- Recon patterns (schema, field distribution)
- Extract → Navigate workflow
- Filter → Compress patterns
- Compare subsets across time

## Danger Zones

❌ **Don't:**
- Start with root of massive projects (use focused subdirs)
- Explore data directories blindly (GBs of files)
- Use tiny budgets on deep hierarchies (unreadable)
- Forget `--deduplicate` for code (wastes 50%+ budget)

✅ **Do:**
- Recon first (30 sec with Unix tools)
- Start focused, expand outward
- Use range for files >1MB
- Use dedup by default for code

## Format Support

**Native:** folders, text, mind maps (`[N]` nodes), Python (AST-aware), Markdown (heading hierarchy)
**Via pipeline:** JSONL (use jq → nub, see above)
**Coming:** JSON, CSV, Conversation logs
