# Protein Analysis

## When
Protein properties: "what's the MW of pX", "protein analysis", "protparam", "isoelectric point", "extinction coefficient", "is this protein stable".

## Tools
- search
- extract
- protparam

## Workflow
1. search() to resolve name to SID (if needed)
2. extract() CDS feature, then protparam(sequence=extracted_seq)
   - OR protparam(sequence=sid:N) if whole sequence is coding
   - OR protparam(sequence=raw_protein) if user provides protein directly

## Report
```python
report["properties"] = r["properties"]  # [{property, value, unit}, ...]
report["composition"] = r["composition"]  # [{amino_acid, name, count, percent}, ...]
```

## Rules
- For a specific CDS, extract() it first -- don't feed the whole plasmid
- protparam auto-translates DNA input, no need to call translate() first
- Do not include the full protein sequence in report unless asked
- 1-2 Python calls, property-value table + composition table
