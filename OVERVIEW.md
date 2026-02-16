# Zerg Browser - Project Overview

A lightweight, Docker-based platform for managing and querying lab sequence data using natural language.

---

## Pain Points Addressed

```
FILES                        PEOPLE                    PROCESS
─────                        ──────                    ───────
• Poor naming                • Newcomers lost          • Cloning is tedious
• Duplicates                 • No one documents        • Human errors
• Scattered structure        • Training burden         • Protocol ignored
• No central index           • Different skill levels  • ELN disconnected

                            ┌─────────┐
                            │   LLM   │
                            │ as glue │
                            └────┬────┘
                                 │
       ┌─────────────────────────┼─────────────────────────┐
       ▼                         ▼                         ▼
  ┌─────────┐              ┌─────────┐              ┌─────────┐
  │ Search  │              │ Design  │              │   ELN   │
  │ & Find  │              │ & Clone │              │  Sync   │
  └─────────┘              └─────────┘              └─────────┘
  ── MVP ──                ── LATER ──              ── LATER ──
```

---

## Full Vision — Module Map

```
MODULE                  DESCRIPTION                          PHASE
──────                  ───────────                          ─────
Crawler + Watcher       Scan /data/, watch for changes       MVP
Parser Engine           sgffp, Biopython parsing             MVP
PostgreSQL Store        Hybrid schema, indexed fields        MVP
BLAST+ Index            Sequence similarity search           MVP
LLM Engine (vLLM)       Intent recognition, param extract    MVP
Tool Router             NL / /cmd / //cmd dispatch           MVP
WebSocket API           Concurrent bidirectional comms       MVP
Svelte Frontend         Chat + widgets + command palette     MVP
─────────────────────────────────────────────────────────────────
External DB Connector   AddGene, NCBI, custom repos          v2
Task Manager            Lab task tracking in sidebar          v2
User Accounts           Auth, per-user history, roles         v2
Cloning Library         Custom Golden Gate, Gibson, etc.      v2
eLabJournal Sync        ELN experiment/sample creation        v2
Export Engine            File export (.gb, .fasta, .dna)      v2
Synonym Table           Feature/resistance name resolution    v2
```

---

## MVP Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      ZERG MVP                                    │
│                                                                  │
│   /data/sequences/                                               │
│   ├── project_A/          ┌──────────────────────────────────┐  │
│   ├── project_B/    ───►  │         FILE WATCHER             │  │
│   └── ...                 │                                   │  │
│                           │  • Startup: full recursive scan   │  │
│                           │  • Runtime: inotify/fswatch       │  │
│                           │  • Rule-based file processing     │  │
│                           │  • Hash-based change detection    │  │
│                           └──────────────┬───────────────────┘  │
│                                          ▼                       │
│                           ┌──────────────────────────────────┐  │
│                           │       PARSER ENGINE              │  │
│                           │                                   │  │
│                           │  .dna ──► sgffp                  │  │
│                           │  .gb  ──► Biopython              │  │
│                           │  .fa  ──► Biopython              │  │
│                           │  .zrt ──► sgffp                  │  │
│                           │                                   │  │
│                           │  Extracts:                        │  │
│                           │  • sequence + topology            │  │
│                           │  • features (name,type,loc,strand)│  │
│                           │  • primers                        │  │
│                           │  • notes / description            │  │
│                           │  • file metadata (path,size,hash) │  │
│                           └───────────┬──────────────────────┘  │
│                                       ▼                          │
│                    ┌──────────────────────────────────────────┐  │
│                    │            STORAGE LAYER                  │  │
│                    │                                           │  │
│                    │  ┌─────────────┐    ┌─────────────────┐  │  │
│                    │  │ PostgreSQL  │    │    BLAST+        │  │  │
│                    │  │             │    │                  │  │  │
│                    │  │ sequences   │    │ makeblastdb      │  │  │
│                    │  │ features    │    │ blastn / blastp   │  │  │
│                    │  │ primers     │    │                  │  │  │
│                    │  │ files       │    │ Rebuilt on every │  │  │
│                    │  │ meta (JSONB)│    │ index change     │  │  │
│                    │  └─────────────┘    └─────────────────┘  │  │
│                    └──────────────────────────────────────────┘  │
│                                       ▲                          │
│                    ┌──────────────────┴───────────────────────┐  │
│                    │          TOOL EXECUTOR                    │  │
│                    │                                           │  │
│                    │  /search  — NLP-powered metadata search  │  │
│                    │  /blast   — sequence similarity           │  │
│                    │  /profile — full sequence details         │  │
│                    │  /browse  — navigate project folders      │  │
│                    │  /status  — health + index stats          │  │
│                    │  /help    — capabilities                  │  │
│                    └──────────────────┬───────────────────────┘  │
│                                       ▲                          │
│                    ┌──────────────────┴───────────────────────┐  │
│                    │           TOOL ROUTER                     │  │
│                    │                                           │  │
│                    │  NL text ──► LLM ──► tool selection       │  │
│                    │  /cmd    ──► LLM ──► specified tool first │  │
│                    │  //cmd   ──► form ──► direct execution    │  │
│                    └──────────────────┬───────────────────────┘  │
│                                       ▲                          │
│           ┌───────────────────────────┴────────────────────────┐ │
│           │              LLM ENGINE (vLLM)                     │ │
│           │                                                     │ │
│           │  Qwen2.5-14B (local, private)                      │ │
│           │  • Intent recognition                               │ │
│           │  • Tool selection + param extraction                │ │
│           │  • Response formatting + summarization              │ │
│           └───────────────────────────┬────────────────────────┘ │
│                                       ▲                          │
│                                       │ WebSocket                │
│                                       │ (concurrent sessions)    │
│           ┌───────────────────────────┴────────────────────────┐ │
│           │           FASTAPI SERVER                           │ │
│           │                                                     │ │
│           │  • WebSocket endpoint (multi-client)               │ │
│           │  • REST endpoints (/health, /api/...)              │ │
│           │  • Static file serving (Svelte build)              │ │
│           │  • Chat storage (server-side JSON)                 │ │
│           └───────────────────────────┬────────────────────────┘ │
│                                       │                          │
└───────────────────────────────────────┼──────────────────────────┘
                                        │
                            ┌───────────┴───────────┐
                            │   SVELTE FRONTEND     │
                            │                        │
                            │  • Chat interface      │
                            │  • Inline widgets      │
                            │  • Command palette     │
                            │  • /  and //  modes    │
                            │  • Chat history list   │
                            └────────────────────────┘
```

---

## Docker Composition (MVP)

```
┌─────────────────┐
│  zerg-server     │  FastAPI + Watcher + Tool Router
│  Python 3.11     │  Serves Svelte static build
│  Port 8080       │  WebSocket endpoint
└────────┬─────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌────────┐
│ postgres│ │ vllm   │
│        │ │        │
│ Port   │ │ GPU    │
│ 5432   │ │ Port   │
│        │ │ 8000   │
└────────┘ └────────┘

Total: 3 containers
No user accounts — but concurrent WebSocket sessions supported.

Volumes:
  /data/sequences  → mounted read-only into zerg-server
  pgdata           → persistent PostgreSQL storage
```

---

## Database Schema (Hybrid)

```
TABLE: sequences
─────────────────────────────────────────────────────────────────
 Column      │ Type        │ Notes
─────────────┼─────────────┼─────────────────────────────────────
 id          │ SERIAL PK   │
 file_id     │ FK          │ → indexed_files.id
 name        │ TEXT        │ Sequence name from file
 size_bp     │ INTEGER     │ Sequence length
 topology    │ TEXT        │ 'circular' | 'linear'
 sequence    │ TEXT        │ Full sequence string
 description │ TEXT        │ Parsed description / notes
 meta        │ JSONB       │ Flexible fields (GIN-indexed)
 created_at  │ TIMESTAMPTZ │
 updated_at  │ TIMESTAMPTZ │

 Indexes: name (trigram), size_bp, topology, meta (GIN)


TABLE: features
─────────────────────────────────────────────────────────────────
 Column      │ Type        │ Notes
─────────────┼─────────────┼─────────────────────────────────────
 id          │ SERIAL PK   │
 seq_id      │ FK          │ → sequences.id
 name        │ TEXT        │ Feature name (GFP, KanR, CMV...)
 type        │ TEXT        │ SO term (CDS, promoter, terminator)
 start       │ INTEGER     │ 0-indexed start position
 end         │ INTEGER     │ 0-indexed end position
 strand      │ SMALLINT    │ +1 or -1
 qualifiers  │ JSONB       │ Additional key-value pairs

 Indexes: name (trigram), type, seq_id


TABLE: primers
─────────────────────────────────────────────────────────────────
 Column      │ Type        │ Notes
─────────────┼─────────────┼─────────────────────────────────────
 id          │ SERIAL PK   │
 seq_id      │ FK          │ → sequences.id
 name        │ TEXT        │ Primer name
 sequence    │ TEXT        │ Primer sequence
 tm          │ REAL        │ Melting temperature
 start       │ INTEGER     │
 end         │ INTEGER     │
 strand      │ SMALLINT    │ +1 or -1


TABLE: indexed_files
─────────────────────────────────────────────────────────────────
 Column      │ Type        │ Notes
─────────────┼─────────────┼─────────────────────────────────────
 id          │ SERIAL PK   │
 file_path   │ TEXT UNIQUE │ Absolute path
 file_hash   │ TEXT        │ SHA256 for change detection
 format      │ TEXT        │ 'dna' | 'gb' | 'fasta' | 'zrt'
 status      │ TEXT        │ 'active' | 'deleted' | 'error'
 error_msg   │ TEXT        │ Parse error if status='error'
 indexed_at  │ TIMESTAMPTZ │
 file_size   │ BIGINT      │ File size in bytes
 file_mtime  │ TIMESTAMPTZ │ File modification time


Fuzzy search: pg_trgm extension
─────────────────────────────────
 CREATE EXTENSION pg_trgm;
 CREATE INDEX idx_seq_name_trgm ON sequences USING gin (name gin_trgm_ops);
 CREATE INDEX idx_feat_name_trgm ON features USING gin (name gin_trgm_ops);
 CREATE INDEX idx_seq_meta ON sequences USING gin (meta);

 Query example:
   SELECT * FROM sequences
   WHERE name % 'green fluorescent'    -- trigram similarity
   OR meta @> '{"tag": "GFP"}'         -- JSONB containment
   ORDER BY similarity(name, 'green fluorescent') DESC;
```

---

## File Watcher — Rule-Based Processing

```yaml
# zerg_config.yaml

watcher:
  root: /data/sequences
  recursive: true
  poll_interval: 5s

rules:
  - match: "*.dna"
    action: parse
    parser: sgffp
    extract: [sequence, features, primers, notes]

  - match: "*.gb"
    action: parse
    parser: biopython
    extract: [sequence, features, description]

  - match: "*.gbk"
    action: parse
    parser: biopython
    extract: [sequence, features, description]

  - match: "*.fasta"
    action: parse
    parser: biopython
    extract: [sequence]

  - match: "*.fa"
    action: parse
    parser: biopython
    extract: [sequence]

  - match: "*.zrt"
    action: parse
    parser: sgffp
    extract: [alignment]

  - match: "*.pdf"
    action: ignore

  - match: "*.docx"
    action: ignore

  - match: ".*"
    action: ignore

  - match: "*"
    action: log
    message: "Unknown file type, skipping"
```

```
WATCHER LIFECYCLE
═════════════════

  Startup                          Runtime
  ───────                          ───────
  1. Load rules from config        1. inotify/fswatch event
  2. Full recursive scan           2. Match file against rules
  3. For each file:                3. If action=parse:
     • Match rules top-down           • Check file_hash
     • Hash file (SHA256)             • Skip if unchanged
     • Check if hash exists           • Parse + upsert DB
       in DB (skip if same)           • Rebuild BLAST index
     • Parse new/changed           4. If action=ignore:
     • Insert/update DB               • Skip silently
     • Rebuild BLAST index         5. If file deleted:
  4. Report: "847 files               • Mark status='deleted'
     indexed, 12 new"                 • Rebuild BLAST index
```

---

## Interaction Modes

```
MODE 1: Natural language
────────────────────────
User: "find all kanamycin resistant plasmids with GFP"
      │
      ▼
LLM interprets → selects tool(s) → executes → responds

MODE 2: Guided command  /command
────────────────────────────────
User: "/search GFP kanamycin"
      │
      ▼
LLM uses search tool first, can chain others if needed

MODE 3: Direct tool  //command
──────────────────────────────
User: "//search"
      │
      ▼
Opens tool UI form, user fills parameters manually, no LLM
```

---

## MVP Toolbox

```
/search     NLP-powered metadata + feature search
            Query by: name, features, resistance, topology,
            size range, project/folder, file type
            Fuzzy matching via pg_trgm

/blast      Sequence similarity (paste or reference by name)
            Results displayed after BLAST+ completion

/profile    Full details of one sequence
            Features, primers, metadata, file info

/browse     Navigate project directory tree
            Show indexed files + basic metadata

/status     System health, indexed file count, LLM status
/help       Explain capabilities
```

---

## Widget System

```
STATE: EXPANDED (user clicked or just received)
┌─────────────────────────────────────────────────────────────────────┐
│ search results                                                [−]   │
│ ─────────────────────────────────────────────────────────────────── │
│ │ NAME        │ SIZE  │ RESISTANCE │ FEATURES         │ ACTIONS │  │
│ ├─────────────┼───────┼────────────┼──────────────────┼─────────│  │
│ │ pEGFP-N1    │ 4.7kb │ Kan        │ GFP, CMV         │ [View]  │  │
│ │ pGFP-Kan    │ 5.2kb │ Kan        │ GFP, T7          │ [View]  │  │
│ └─────────────┴───────┴────────────┴──────────────────┴─────────┘  │
│                                                     [BLAST all]     │
└─────────────────────────────────────────────────────────────────────┘

STATE: COLLAPSED (user clicked away / focused prompt)
┌──────────────────────────────────────────┐
│ search: 8 results                   [+]  │  ← click to expand
└──────────────────────────────────────────┘

Widgets re-execute tool on expand (fresh data, reproducible)
```

---

## Chat Storage

```
Storage directory: configurable via ZERG_CHAT_DIR env var
Default: /var/zerg/chats/

File naming: {hash}-{date}.json

Example: a1b2c3d4-2025-01-31.json

{
  "id": "a1b2c3d4",
  "created": "2025-01-31T10:00:00Z",
  "messages": [
    {
      "role": "user",
      "content": "find GFP plasmids with kanamycin",
      "ts": "2025-01-31T10:00:01Z"
    },
    {
      "role": "assistant",
      "content": "Found 8 plasmids matching your criteria:",
      "widget": {
        "type": "table",
        "tool": "search",
        "params": {
          "query": "GFP",
          "filters": {"resistance": "kanamycin"}
        },
        "summary": "8 results"
      },
      "ts": "2025-01-31T10:00:03Z"
    }
  ]
}

• No user field (no accounts in MVP)
• JSON stores only tool + params (no cached data)
• Widget re-executes on expand for fresh results
• Clean, reproducible, replayable
```

---

## Technology Stack

### Backend
- **Python 3.11+** — Primary language
- **FastAPI** — API + WebSocket server
- **PostgreSQL** — Hybrid schema with pg_trgm fuzzy search
- **BLAST+** — Sequence similarity (local binary, rebuilt on change)

### File Parsing
- **sgffp** — SnapGene .dna and .zrt files (primary)
- **Biopython** — GenBank .gb and FASTA .fa/.fasta files

### LLM
- **vLLM** — Inference server
- **Model** — Qwen2.5-14B or similar (thin NLP glue)

### Frontend
- **Svelte** — UI framework
- **Bun** — Runtime + bundler

---

## File Format Support

| Format | Parser | Richness |
|--------|--------|----------|
| .dna (SnapGene) | sgffp | Full (sequence, features, primers, notes, history) |
| .gb/.gbk (GenBank) | Biopython | Good (sequence, features, description) |
| .fasta/.fa | Biopython | Sequence only |
| .zrt (SnapGene alignment) | sgffp | Alignment data |

---

## LLM Role

```
THIN NLP GLUE
─────────────
✓ Intent recognition
✓ Tool selection
✓ Parameter extraction
✓ Response formatting
✓ Summarize results
✓ Suggest next actions
```

Model sizing:
- 14B model handles tool use + summarization well
- Fits in 24GB VRAM
- Fast (~50-60 tok/s)

---

## UI Layout (MVP)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  ZERG BROWSER                                                     [⚙]      │
├─────────────────┬───────────────────────────────────────────────────────────┤
│                 │                                                            │
│  Chat History   │   ┌────────────────────────────────────────────────────┐  │
│  ─────────────  │   │  Chat messages + inline widgets                    │  │
│  > GFP search   │   │                                                     │  │
│  > BLAST run    │   │  [Collapsible result widgets]                       │  │
│  > Kan vectors  │   │                                                     │  │
│                 │   │                                                     │  │
│                 │   └────────────────────────────────────────────────────┘  │
│                 │                                                            │
│                 │   ┌────────────────────────────────────────────────────┐  │
│                 │   │ Type message or /command...                    [>] │  │
│                 │   └────────────────────────────────────────────────────┘  │
│                 │    / opens command palette                                 │
│                 │                                                            │
└─────────────────┴────────────────────────────────────────────────────────────┘
```

---

## Key Decisions

| Aspect | Decision | Rationale |
|--------|----------|-----------|
| Architecture | Lightweight, 3 containers | Simple, fast deployment |
| DB Schema | Hybrid: core tables + JSONB meta | Fast queries + flexibility |
| Fuzzy Search | pg_trgm extension | Efficient, no extra service |
| Storage | PostgreSQL + BLAST+ | Proven, sufficient |
| LLM | Local 14B model | Privacy, speed, cost |
| Frontend | Custom Svelte + Bun | Full control, minimal |
| Chat format | JSON with tool params only | Clean, reproducible |
| Chat location | Server-side, admin-configurable | Persistent, shared access |
| File parsing | sgffp primary, Biopython secondary | Best SnapGene support |
| File watcher | Rule-based YAML config | Flexible, declarative |
| BLAST rebuild | On every index change | Simple for MVP, fast enough |
| Concurrency | Multi-client WebSocket, no auth | MVP simplicity |
| Cloning | Deferred to v2 (custom library) | Focus MVP on search |
| ELN | Deferred to v2 | Focus MVP on search |

---

## Future Roadmap (v2+)

```
v2 ADDITIONS
────────────
• Custom cloning library (Golden Gate, Gibson, restriction/ligation)
• eLabJournal integration (experiments, samples, protocols)
• External DB connectors (AddGene, NCBI)
• User accounts + roles
• Task manager (sidebar panel)
• Export engine (.gb, .fasta, .dna)
• Feature synonym table for smarter search
• /compare tool (side-by-side sequences)
• /design, /primers, /annotate tools
• Cloud model option (later stage)
```
