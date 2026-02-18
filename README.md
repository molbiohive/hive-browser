# Zerg Browser

Local-first lab sequence search platform with natural language queries powered by LLM.

Zerg Browser watches your local directories for biological sequence files (.dna, .rna, .prot, .gb, .fasta), indexes them into a PostgreSQL database, and lets you search, explore, and compare sequences through a chat interface — using either natural language or direct commands.

## Why Zerg?

Zerg is a reference to the species from the StarCraft universe, known for rapid mutation and adaptation. This tool helps you tame the beast — rapidly growing and changing sequence data scattered across lab file systems.

## Features

- **Natural language search** — ask "find all GFP plasmids" or "show me ampicillin-resistant constructs"
- **BLAST integration** — paste a sequence to find similar constructs in your collection
- **File watching** — automatically indexes new and changed files
- **Multiple formats** — SnapGene (.dna, .rna, .prot), GenBank (.gb), FASTA (.fasta)
- **Fuzzy matching** — finds results even with approximate names (pg_trgm)
- **Local-first** — your data stays on your machine, LLM runs locally via Ollama
- **Cloud LLM support** — optionally use Anthropic, OpenAI, or any provider via litellm
- **Extensible tools** — add new tools by dropping a Python file + Svelte widget

## Quick Start

### Prerequisites

- Python 3.12+
- PostgreSQL with pg_trgm extension
- BLAST+ command-line tools
- [Ollama](https://ollama.com) (or a cloud LLM API key)
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- [bun](https://bun.sh) (frontend package manager)

### Setup

```bash
git clone https://github.com/merv1n34k/zerg-browser.git
cd zerg-browser
make setup    # installs deps, sets up DB, pulls Ollama model
```

Copy and edit the config:

```bash
cp config/config.example.yaml config/config.local.yaml
# Edit paths, database URL, LLM settings
export ZERG_CONFIG=config/config.local.yaml
```

### Run

```bash
make dev            # Backend on :8080
make dev-frontend   # Frontend on :5173 (in another terminal)
```

Open http://localhost:5173 and start searching.

## Architecture

```
Browser  <-->  Svelte 5 frontend  <-->  FastAPI + WebSocket  <-->  PostgreSQL
                                            |
                                        Tool system
                                       /     |     \
                                  Search   BLAST   Profile ...
                                            |
                                     Ollama / litellm
```

**Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic, sgffp, Biopython

**Frontend**: Svelte 5 (runes), SvelteKit, marked (markdown)

**LLM**: Ollama with qwen2.5:7b (recommended) or any litellm-supported provider

### Tool System

Tools are self-describing. Each tool declares its name, schema, widget type, and execution logic. Adding a new tool:

1. Create `src/zerg/tools/mytool.py` with a `Tool` subclass and `create()` factory
2. Create `frontend/src/lib/MyToolWidget.svelte`

Everything else is auto-generated: system prompt, command palette, help text, widget dispatch.

## Commands

| Syntax | Mode | Example |
|--------|------|---------|
| Free text | LLM picks tool | `find circular plasmids over 5kb` |
| `/command` | LLM-assisted | `/search ampicillin` |
| `//command` | Direct execution | `//profile {"name": "pUC19"}` |
| `/help` | List commands | `/help` |

## Testing

```bash
uv run pytest -v    # 36 tests (parsers, ingestion, watcher rules)
```

## License

AGPL-3.0 — free for personal and open source use. Commercial licensing
available for proprietary deployments. See [CONTRIBUTING.md](CONTRIBUTING.md)
for contributor terms or contact merv1n@proton.me for licensing inquiries.
