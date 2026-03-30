# Sequence Alignment

## When
Align multiple sequences: "align these sequences", "compare pX, pY, pZ".

## Tools
- search
- align

## Workflow
1. If names given, search() to resolve SIDs
2. align(sids=[...]) — uses MAFFT

## Report
```python
report["alignment"] = a
```

align() returns widget-ready data — pass through as-is.

## Rules
- Need at least 2 sequences
- Large sequences (>50kb) may be slow
- MAFFT must be installed (dependency)
- 1-2 Python calls
- Pass alignment result through untampered
