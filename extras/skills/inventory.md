# Inventory

## When
List all sequences in the database, show everything available.

## Tools
- search

## Workflow
1. search(query="*")
2. Build sorted table

## Report
```python
report["inventory"] = [
    {"name": r["name"], "size_bp": r["size_bp"],
     "topology": r["topology"], "tags": ", ".join(r["tags"] or [])}
    for r in sorted(results["results"], key=lambda x: x["name"])
]
```

## Rules
- Do not list features per sequence — too noisy
- If > 100 sequences, show count and suggest filtering
- 1 tool call, 1 table, 1 Python call
