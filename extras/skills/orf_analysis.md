# ORF Analysis

## When
Find ORFs: "find ORFs in pX", "open reading frames", "what ORFs are in this sequence", "longest ORF".

## Tools
- search
- orf_find
- protparam

## Workflow
1. search() to resolve name to SID (if needed)
2. orf_find(sequence=sid:N) or orf_find(sequence=raw_dna)
3. Optionally protparam(sequence=top_orf_protein) for the longest ORF

## Report
```python
report["summary"] = [
    {"property": "Sequence length", "value": f"{r['sequence_length']} bp"},
    {"property": "ORFs found", "value": str(r['total_orfs'])},
]
report["orfs"] = [
    {"frame": o["frame"], "start": o["start"], "end": o["end"],
     "length": f"{o['length_nt']} nt / {o['length_aa']} aa",
     "status": o["status"]}
    for o in r["orfs"]
]
```

## Red Flags
- Default min_length is 100 nt -- lower it for short sequences
- Do not include full protein sequences in ORF table -- too long
- Truncate protein to first 20 chars + "..." if showing

## Rules
- 1-2 Python calls, summary table + ORF table
