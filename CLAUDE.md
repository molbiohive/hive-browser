# CLAUDE.md - AI Assistant Guidelines

Instructions for AI assistants working on this molecular biology LLM-enhanced browser project.

---

## Project Context

This is a **Python-based platform** that combines:
- Local LLM inference for natural language queries
- Molecular biology data management (DNA/RNA/protein sequences)
- File parsing and synchronization
- Cloning design and primer tools

**Domain**: Synthetic biology, bioinformatics, laboratory data management.

---

## General Principles

### 1. Domain Expertise Required

When working on this codebase:
- Understand basic molecular biology concepts (plasmids, features, primers, cloning)
- Know SBOL (Synthetic Biology Open Language) standards
- Be familiar with sequence file formats (.dna, .gb, .fasta)
- Understand cloning methods (Gibson, Golden Gate, restriction/ligation)

### 2. Privacy-First Architecture

- All LLM inference runs locally (no external API calls)
- Sequence data never leaves the local network
- No telemetry or data transmission to external services
- Air-gap compatible deployment

### 3. Code Quality Standards

```python
# Always use type hints
def parse_sequence(filepath: Path) -> SequenceRecord:
    ...

# Use Pydantic for data models
class Feature(BaseModel):
    name: str
    type: FeatureType
    start: int
    end: int
    strand: Literal[1, -1]
    qualifiers: dict[str, str] = {}

# Async for I/O operations
async def fetch_from_repository(uri: str) -> SBOLDocument:
    ...
```

### 4. Error Handling

- Never silently fail on biological data operations
- Validate sequences before processing
- Provide meaningful error messages for lab users
- Log all sync/parse operations for debugging

---

## Technology Stack

### Core
- **Python 3.11+** - Primary language
- **FastAPI** - API framework
- **Pydantic** - Data validation
- **SQLAlchemy** - Database ORM
- **Redis** - Job queue and caching

### Molecular Biology
- **Biopython** - Sequence manipulation
- **pydna** - Cloning simulation
- **pySBOL** - SBOL document handling

### LLM Integration
- **vLLM** - High-performance inference server
- **OpenAI-compatible API** - Standard interface

### Infrastructure
- **Docker Compose** - Service orchestration
- **PostgreSQL** - Metadata storage
- **Elasticsearch** - Full-text search

---

## Working with Biological Data

### Sequence Handling

```python
# Always validate sequences
def validate_dna_sequence(seq: str) -> bool:
    valid_chars = set("ATGCNRYSWKMBDHV")
    return all(c.upper() in valid_chars for c in seq)

# Handle topology correctly
class SequenceRecord:
    sequence: str
    topology: Literal["circular", "linear"]

    def is_circular(self) -> bool:
        return self.topology == "circular"
```

### Feature Annotations

- Preserve all feature qualifiers during parsing
- Use Sequence Ontology (SO) terms for feature types
- Maintain strand information (+1/-1)
- Handle overlapping features correctly

### Primer Design

- Always calculate Tm using nearest-neighbor method
- Check for secondary structures (hairpins, dimers)
- Validate primer binding sites on template
- Include GC content and length constraints

---

## LLM Tool Development

### Tool Schema Pattern

```python
from pydantic import BaseModel, Field

class SearchInput(BaseModel):
    """Input schema for search tool."""
    query: str = Field(..., description="Search query text")
    filters: dict = Field(default_factory=dict, description="Optional filters")
    limit: int = Field(default=20, ge=1, le=100)

class SearchResult(BaseModel):
    """Single search result."""
    id: str
    name: str
    description: str | None
    score: float

class SearchOutput(BaseModel):
    """Output schema for search tool."""
    results: list[SearchResult]
    total: int
    query: str
```

### Tool Implementation Pattern

```python
async def execute_search(input: SearchInput) -> SearchOutput:
    """
    Execute search against the database.

    This tool is called by the LLM when users ask to find sequences,
    plasmids, or features by name, description, or other criteria.
    """
    # 1. Validate input
    if not input.query.strip():
        raise ValueError("Search query cannot be empty")

    # 2. Execute search
    results = await database.search(
        query=input.query,
        filters=input.filters,
        limit=input.limit
    )

    # 3. Format output for LLM
    return SearchOutput(
        results=[SearchResult(**r) for r in results],
        total=len(results),
        query=input.query
    )
```

### Tool Registration

Tools should be:
- Self-documenting (clear docstrings)
- Idempotent where possible
- Return structured data (not raw API responses)
- Handle errors gracefully

---

## File Parsing Guidelines

### SnapGene (.dna) Files

```python
from sgffp import SgffReader

def parse_snapgene(filepath: Path) -> dict:
    """Parse SnapGene file and extract all metadata."""
    sgff = SgffReader.from_file(filepath)

    return {
        "sequence": sgff.sequence.value,
        "topology": sgff.sequence.topology,
        "features": [parse_feature(f) for f in sgff.features],
        "primers": [parse_primer(p) for p in sgff.primers],
        "notes": sgff.notes,
    }
```

### GenBank (.gb) Files

```python
from Bio import SeqIO

def parse_genbank(filepath: Path) -> dict:
    """Parse GenBank file."""
    record = SeqIO.read(filepath, "genbank")

    return {
        "sequence": str(record.seq),
        "topology": record.annotations.get("topology", "linear"),
        "features": [parse_biopython_feature(f) for f in record.features],
        "description": record.description,
    }
```

### SBOL Documents

```python
from sbol2 import Document, ComponentDefinition

def parse_sbol(filepath: Path) -> list[dict]:
    """Parse SBOL document."""
    doc = Document()
    doc.read(str(filepath))

    results = []
    for comp in doc.componentDefinitions:
        results.append({
            "uri": comp.identity,
            "name": comp.displayId,
            "sequence": get_sequence(comp),
            "annotations": parse_annotations(comp),
        })

    return results
```

---

## API Design Patterns

### WebSocket Protocol

```python
# Message types
class MessageType(str, Enum):
    MESSAGE = "message"      # User input
    STREAM = "stream"        # Streaming response
    TOOL_CALL = "tool_call"  # Tool invocation
    TOOL_RESULT = "tool_result"  # Tool output
    DONE = "done"            # Response complete
    ERROR = "error"          # Error occurred

# Message format
class WSMessage(BaseModel):
    type: MessageType
    id: str  # Unique message ID
    content: Any
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

### REST API Structure

```
GET  /api/search?q=...&filters=...    # Search sequences
GET  /api/sequences/{id}              # Get sequence details
POST /api/blast                       # BLAST search
POST /api/design                      # Cloning design
GET  /api/collections                 # List collections
POST /api/collections/{id}/upload     # Upload to collection
```

---

## Testing Guidelines

### Unit Tests

```python
import pytest
from myapp.parsers import parse_snapgene

def test_parse_circular_plasmid():
    result = parse_snapgene(Path("tests/fixtures/pUC19.dna"))

    assert result["topology"] == "circular"
    assert len(result["sequence"]) == 2686
    assert any(f["name"] == "lacZ" for f in result["features"])

def test_parse_invalid_file():
    with pytest.raises(ParseError):
        parse_snapgene(Path("tests/fixtures/invalid.dna"))
```

### Integration Tests

```python
@pytest.mark.integration
async def test_search_tool_integration():
    # Setup test data
    await database.insert(test_plasmid)

    # Execute search
    result = await execute_search(SearchInput(query="GFP"))

    # Verify
    assert result.total > 0
    assert any("GFP" in r.name for r in result.results)
```

### LLM Tool Tests

```python
def test_tool_schema_valid():
    """Ensure tool schema is valid for LLM."""
    schema = SearchInput.model_json_schema()

    # All required fields documented
    assert "description" in schema["properties"]["query"]

    # Defaults specified
    assert schema["properties"]["limit"]["default"] == 20
```

---

## Documentation Standards

### Code Documentation

```python
def design_gibson_assembly(
    insert: SequenceRecord,
    vector: SequenceRecord,
    insertion_site: int | str,
    overlap_length: int = 25,
) -> GibsonDesign:
    """
    Design Gibson assembly for inserting a sequence into a vector.

    Args:
        insert: The sequence to be inserted
        vector: The destination vector
        insertion_site: Position (int) or feature name (str) for insertion
        overlap_length: Length of homology arms (default: 25bp)

    Returns:
        GibsonDesign containing primers, expected product, and assembly plan

    Raises:
        DesignError: If insertion site is invalid or primers cannot be designed

    Example:
        >>> design = design_gibson_assembly(gfp_gene, pet28, "MCS")
        >>> print(design.forward_primer.sequence)
        'ATGGTGAGCAAGGGCGAGGAG...'
    """
```

### API Documentation

- Use OpenAPI/Swagger for REST endpoints
- Include request/response examples
- Document error codes and meanings
- Provide curl examples for common operations

---

## Deployment Considerations

### Docker Best Practices

```dockerfile
# Multi-stage build
FROM python:3.11-slim as builder
WORKDIR /app
COPY pyproject.toml poetry.lock ./
RUN pip install poetry && poetry export -f requirements.txt > requirements.txt

FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /app/requirements.txt .
RUN pip install -r requirements.txt
COPY src/ ./src/
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Health Checks

```python
@app.get("/health")
async def health_check():
    """Health check endpoint for container orchestration."""
    checks = {
        "database": await check_database(),
        "redis": await check_redis(),
        "llm": await check_llm_service(),
    }

    all_healthy = all(checks.values())
    return {
        "status": "healthy" if all_healthy else "degraded",
        "checks": checks,
    }
```

---

## Common Pitfalls

### Avoid These Mistakes

1. **Hardcoding sequences** - Always parameterize
2. **Ignoring strand** - Features can be on either strand
3. **Assuming linear** - Many lab sequences are circular
4. **Silent failures** - Always log and report errors
5. **Blocking I/O** - Use async for network/file operations
6. **No validation** - Validate all biological data input
7. **Missing context** - Provide enough info in LLM prompts

### Biology-Specific Issues

1. **Circular sequence handling** - Wrap indices correctly
2. **Reverse complement** - Remember to reverse AND complement
3. **Codon tables** - Use correct table for organism
4. **Feature coordinates** - 0-indexed vs 1-indexed
5. **Tm calculation** - Use appropriate formula for primer length

---

## References

- **PROTOCOL.md** - Technical specifications for this project
- **Biopython Tutorial** - https://biopython.org/DIST/docs/tutorial/Tutorial.html
- **SBOL Standard** - https://sbolstandard.org/
- **pydna Documentation** - https://pydna-group.github.io/pydna/
