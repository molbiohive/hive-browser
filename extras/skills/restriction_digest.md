# Restriction Digest

## When
Digest a sequence with specific enzymes: "cut pX with EcoRI and BamHI", "digest with NotI".

## Workflow
1. digest(sequence=..., reactions=["EcoRI", "BamHI"]) — use + for co-digestion: "EcoRI+BamHI"

## Report
```python
report["digest"] = d
```

digest() returns widget-ready data including gel visualization — pass through as-is.

## Red Flags
- Enzyme names must be exact (e.g. "EcoRI" not "ecori")
- Use + in reaction string for co-digestion: ["EcoRI+BamHI"] = one lane
- Separate entries = separate lanes: ["EcoRI", "BamHI"] = two lanes

## Rules
- 1 Python call
- digest result includes gel_data — do not tamper, pass through
