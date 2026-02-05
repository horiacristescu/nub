# JSONL Exploration with jq + nub

Nub treats JSONL as text (no JSON parsing). Use **jq + nub pipeline** for structured exploration.

## Recon First

```bash
wc -l data.jsonl                           # Line count
ls -lh data.jsonl                          # File size
head -1 data.jsonl | jq 'keys'             # Schema (field names)
head -1 data.jsonl | jq '.'                # Full first record
```

## Field Distribution

```bash
# Count by field value
jq -r '.status' data.jsonl | sort | uniq -c | sort -rn | head -20
jq -r '.type // "null"' data.jsonl | sort | uniq -c | sort -rn

# Time range
jq -r '.timestamp' data.jsonl | sort | head -1  # First
jq -r '.timestamp' data.jsonl | sort | tail -1  # Last

# Group by month
jq -r '.timestamp[:7]' data.jsonl | sort | uniq -c
```

## Extract → Navigate Pattern

```bash
# 1. Extract key fields to temp file
jq -r '"\(.time) | \(.topic[0:40]) | \(.title[0:50])"' data.jsonl > /tmp/index.txt

# 2. Navigate with nub
nub /tmp/index.txt --range 1:100 --shape 100:30       # First 100
nub /tmp/index.txt --range 500:600 --shape 100:30    # Middle section

# 3. Find targets, then zoom
grep -n "error" /tmp/index.txt | head -10             # Find line numbers
nub /tmp/index.txt --range 450:470 --shape 100:25    # Zoom to hits
```

## Filter → Compress Pattern

```bash
# Filter by field, then compress
jq -c 'select(.type == "error")' data.jsonl | nub --shape 120:40

# Filter by time range
jq -c 'select(.time | startswith("2024-08"))' data.jsonl | nub --shape 120:40

# Filter + extract
jq -r 'select(.status == "failed") | "\(.id) | \(.message)"' data.jsonl | nub --shape 100:30
```

## Compare Subsets

```bash
# Compare two time periods
jq -r 'select(.time | startswith("2024-03")) | .category' data.jsonl | sort | uniq -c | sort -rn
jq -r 'select(.time | startswith("2025-03")) | .category' data.jsonl | sort | uniq -c | sort -rn

# Sample from filtered subset
jq -r 'select(.topic | test("keyword")) | .title' data.jsonl | shuf | head -20
```

## Full Workflow Example

Exploring a conversation archive:

```bash
# 1. Recon
wc -l chunks.jsonl                                    # 17157 lines
ls -lh chunks.jsonl                                   # 79MB
head -1 chunks.jsonl | jq 'keys'                      # [time, title, topic, text, ...]

# 2. Understand distribution
jq -r '.source_name' chunks.jsonl | sort | uniq -c    # openai: 9340, anthropic: 6394
jq -r '.parent_topic' chunks.jsonl | sort | uniq -c | sort -rn | head -10

# 3. Extract index
jq -r '"\(.time) | \(.topic[0:40]) | \(.title[0:50])"' chunks.jsonl > /tmp/idx.txt

# 4. Navigate
nub /tmp/idx.txt --range 1:100 --shape 100:30         # Browse start
grep -n "Chinese Room" /tmp/idx.txt | head            # Find targets
nub /tmp/idx.txt --range 125:140 --shape 100:25       # Zoom to hit

# 5. Deep dive on specific entry
jq -r 'select(.id == "specific-id") | .text' chunks.jsonl | nub --shape 100:50
```

## Why jq + nub?

| Tool | Strength |
|------|----------|
| **jq** | Streaming JSON, handles GBs, filters/transforms fields |
| **nub** | Compresses text to budget, preserves structure |
| **Pipeline** | jq reduces data, nub makes it readable |

Don't try to make nub parse JSON - use the right tool for each job.
