# Codon Analysis

## When
Codon usage: "codon usage of pX", "rare codons", "codon optimization", "RSCU", "codon bias".

## Tools
- search
- extract
- codon_usage

## Workflow
1. search() to resolve name to SID (if needed)
2. extract() CDS feature to get coding sequence
3. codon_usage(sequence=extracted_seq)

## Report
```python
report["summary"] = [
    {"property": "Total codons", "value": str(r["total_codons"])},
    {"property": "Rare codons", "value": str(len(r["rare_codons"]))},
]
report["rare_codons"] = [
    {"codon": c["codon"], "amino_acid": c["amino_acid"],
     "count": c["count"], "frequency": f"{c['frequency']:.4f}",
     "rscu": f"{c['rscu']:.2f}"}
    for c in r["rare_codons"]
]
# Full table only if user asks
report["codons"] = r["codons"]
```

## Red Flags
- Feed coding DNA only -- not a whole plasmid
- extract() the CDS first for accurate codon usage
- Use table=11 for bacterial sequences

## Rules
- 1-2 Python calls, summary + rare codon table (full table on request)
