# Similarity Search

## When
Find similar sequences, homologs, or compare a query sequence against the database.

## Tools
- search
- blast

## Workflow
1. If user gives a name, search() first to get SID
2. blast(sequence=...) — auto-detects program

## Report
```python
report["blast_hits"] = [
    {"name": h["subject"], "identity": f"{h['identity']:.1f}%",
     "evalue": f"{h['evalue']:.1e}", "score": h["bitscore"]}
    for h in r["hits"]
]
```

## Rules
- BLAST needs a sequence string or sid:N, not a name
- search() does text matching, BLAST does alignment — different tools
- Short sequences (<30bp) may need lower word_size
- 1-2 Python calls (resolve name + blast)
- 1 report table, do not profile each hit
