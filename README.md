# Zerg Browser

Local-first lab sequence search platform with natural language queries powered by LLM.

Zerg Browser watches your local directories for biological sequence files (.dna, .rna, .prot, .gb, .fasta), indexes them into a PostgreSQL database, and lets you search, explore, and compare sequences through a chat interface — using either natural language or direct commands.

## Why Zerg?

Zerg is a reference to the species from the StarCraft universe, known for rapid mutation and adaptation. This tool helps you tame the beast — rapidly growing and changing sequence data scattered across lab file systems.

## Features

- **Natural language search** — ask "find all GFP plasmids" or "show me ampicillin-resistant constructs"
- **BLAST integration** — paste a sequence to find similar constructs in your collection
- **Agentic tool chaining** — complex queries like "blast the AmpR promoter from pUC19" are automatically broken into extract → blast steps
- **Sequence analysis** — translate, transcribe, digest, GC content, reverse complement
- **File watching** — automatically indexes new and changed files
- **Multiple formats** — SnapGene (.dna, .rna, .prot), GenBank (.gb), FASTA (.fasta)
- **Fuzzy matching** — finds results even with approximate names (pg_trgm)
- **Local-first** — your data stays on your machine, LLM runs locally via Ollama
- **Cloud LLM support** — optionally use Anthropic, OpenAI, or any provider via litellm
- **Extensible tools** — add custom tools by dropping a Python file in the tools directory

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

make check-deps   # verify uv, bun, psql, blastn, ollama are installed
make setup        # install deps, create configs, set up DB, run migrations
```

Edit `config/config.local.yaml` with your paths, database URL, and LLM settings.

### Run

```bash
make back-dev     # Backend on :8080
make front-dev    # Frontend on :5173 (in another terminal)
```

Open http://localhost:5173 and start searching.

## Architecture

```
Browser  <-->  Svelte 5 frontend  <-->  FastAPI + WebSocket  <-->  PostgreSQL
                                            |
                                       Tool Router
                                      /     |      \
                               SIMPLE    LOOP      Direct
                              (3-step)  (agentic)  (//cmd)
                                 |         |
                            Tool System (13 tools)
                           /    |    |    |    \
                       Search BLAST Extract Digest ...
                                 |
                          Ollama / litellm
```

**Backend**: Python 3.12, FastAPI, SQLAlchemy (async), Pydantic, sgffp, Biopython

**Frontend**: Svelte 5 (runes), SvelteKit, marked (markdown)

**LLM**: Ollama with qwen2.5:7b (recommended) or any litellm-supported provider

### Tool System

Tools are self-describing and auto-discovered. Each tool declares its name, schema, tags, widget type, and execution logic.

| Tool | Tags | Description |
|------|------|-------------|
| search | llm, search | Fuzzy name/feature/description search |
| blast | llm, search | BLAST sequence similarity search |
| profile | llm, info | Sequence detail view |
| extract | llm, analysis | Get subsequence by feature, primer, or region |
| translate | llm, analysis | DNA/RNA to protein translation |
| transcribe | llm, analysis | DNA to mRNA transcription |
| digest | llm, analysis | Restriction enzyme cut sites and fragments |
| gc | llm, analysis | GC content and nucleotide composition |
| revcomp | llm, analysis | Reverse complement |
| features | llm, info | List features on a sequence |
| primers | llm, info | List primers on a sequence |
| status | info | Database stats and health |
| model | info | LLM config and connection status |

### LLM Modes

The LLM self-selects between two modes:

- **SIMPLE** — 3-step flow (select tool → extract params → summarize). Used for straightforward queries like "search GFP".
- **LOOP** — Agentic loop that chains multiple tools. Used when the query requires extracting data from one tool to feed into another, e.g. "translate the GFP CDS from pEGFP-N1" → extract → translate.

## Commands

| Syntax | Mode | Example |
|--------|------|---------|
| Free text | LLM picks mode + tool | `blast the AmpR promoter from pUC19` |
| `/command` | LLM-assisted | `/search ampicillin` |
| `//command` | Direct execution | `//digest {"sequence":"GAATTC","enzymes":["EcoRI"]}` |
| `/help` | List commands | `/help` |

## Data Storage

Zerg stores its working data in `~/.zerg/` by default (configurable in YAML config):

```
~/.zerg/
├── blast/       # BLAST database index files (rebuilt on ingestion)
├── chats/       # Chat history as JSON files (auto-saved)
└── tools/       # External tool plugins (*.py, auto-discovered)
```

- **BLAST index** — rebuilt automatically when files are ingested. Path: `blast.db_path`
- **Chat history** — each chat saved as a JSON file with messages, widgets, and chain data. Path: `chat.storage_dir`
- **External tools** — drop a `.py` file here to add custom tools. Must import from `zerg.sdk` only. Path: `tools.directory`

All paths are configurable in `config/config.local.yaml`.

## Development

### Makefile Targets

| Target | Description |
|--------|-------------|
| `make setup` | Full setup: deps + config + db + migrate |
| `make deps` | Install Python + frontend dependencies |
| `make config` | Create config files (if missing) + `~/.zerg/` directories |
| `make db` | Create PostgreSQL database + pg_trgm extension |
| `make migrate` | Run Alembic database migrations |
| `make back-dev` | Start backend with hot reload on :8080 |
| `make front-dev` | Start frontend dev server on :5173 |
| `make static` | Build frontend into `static/` |
| `make prod` | Build frontend + start production server |
| `make test` | Run pytest |
| `make lint` | Run ruff linter |
| `make check-deps` | Verify system tools (uv, bun, psql, blastn, ollama) |
| `make check-backend` | Lint + test |
| `make check-frontend` | Build frontend (catches Svelte compilation errors) |
| `make check-all` | check-deps + check-backend + check-frontend |
| `make clean` | Remove build artifacts and caches |

### Checking for Issues

**Backend:**

```bash
make check-backend    # lint + test in one step

# Or separately
make lint             # ruff check src/ tests/
make test             # uv run pytest -v

# Run specific tests
uv run pytest tests/test_tools.py -v
uv run pytest tests/test_tools.py::TestToolFactoryInternal -v

# Quick import sanity check
uv run python -c "
from zerg.tools.factory import ToolFactory
from zerg.config import Settings
r = ToolFactory.discover(Settings())
print(f'{len(r.all())} tools discovered')
"
```

**Frontend:**

```bash
make check-frontend   # catches Svelte compilation errors
make front-dev        # or run dev server to see warnings live
```

**Full pre-commit check:**

```bash
make check-all
```

### Project Structure

```
src/zerg/
├── main.py              # Entry point (create_app)
├── config.py            # Settings from YAML
├── db/                  # SQLAlchemy models + async session
├── parsers/             # File parsers (snapgene, genbank, fasta)
├── watcher/             # File system watcher + ingestion
├── tools/               # Tool system (13 tools + router + factory)
│   ├── base.py          # Tool ABC, ToolRegistry
│   ├── factory.py       # Auto-discovery (internal + external)
│   ├── router.py        # Dispatch: direct / guided / SIMPLE / LOOP
│   └── *.py             # Individual tools
├── sdk/                 # Public SDK for external tools
├── llm/                 # LLM client + prompts
├── server/              # FastAPI app, routes, WebSocket
└── chat/                # JSON file-based chat persistence

frontend/src/lib/
├── stores/chat.ts       # Svelte stores (messages, config, toolList)
├── Chat.svelte          # Main chat view
├── MessageBubble.svelte # Message rendering with markdown
├── Widget.svelte        # Widget dispatcher (auto-discovers *Widget.svelte)
├── ChainSteps.svelte    # Collapsible agentic chain steps
├── *Widget.svelte       # Individual widgets (Table, Blast, Profile, etc.)
├── FormWidget.svelte    # Dynamic form for tool params
├── CommandPalette.svelte # "/" command autocomplete
└── Sidebar.svelte       # Chat history list
```

## License

AGPL-3.0 — free for personal and open source use. Commercial licensing
available for proprietary deployments. See [CONTRIBUTING.md](CONTRIBUTING.md)
for contributor terms or contact merv1n@proton.me for licensing inquiries.
