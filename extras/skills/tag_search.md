# Tag Search

## When
Search within a specific project or directory: "show plasmids in vectors folder", "what's in the cloning project".

## Workflow
1. search(query="*", tags="<directory_name>")

## Report
```python
report["sequences"] = [
    {"name": r["name"], "size_bp": r["size_bp"],
     "topology": r["topology"]}
    for r in results["results"]
]
```

## Red Flags
- tags param matches directory/folder context, not biological tags
- Use query="*" with tags to list all in a directory

## Rules
- 1 Python call, 1 table
