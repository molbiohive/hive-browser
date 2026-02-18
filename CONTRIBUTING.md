# Contributing to Zerg Browser

Thank you for your interest in contributing to Zerg Browser! This document
outlines the process for contributing and the legal terms that apply to all
contributions.

## Licensing

Zerg Browser is dual-licensed:

- **AGPL-3.0** for open source and community use
- **Commercial license** for proprietary use

To maintain the ability to offer both licensing options, all contributions must
be submitted under the Contributor License Agreement below.

## Contributor License Agreement (CLA)

**By submitting a contribution (pull request, patch, code, documentation, or any
other material) to this project, you accept and agree to the following terms and
conditions for your present and future contributions.**

### 1. Definitions

"Contribution" means any original work of authorship, including any
modifications or additions to existing work, that you intentionally submit to
this project for inclusion. "Submit" means any form of electronic or written
communication sent to the project, including but not limited to pull requests,
patches, commits, issues, and comments.

"Project Author" means Oleksii Stroganov (merv1n@proton.me), the copyright
holder and maintainer of Zerg Browser.

### 2. Grant of Rights

You hereby grant to the Project Author a perpetual, worldwide, non-exclusive,
no-charge, royalty-free, irrevocable copyright license to reproduce, prepare
derivative works of, publicly display, publicly perform, sublicense, and
distribute your Contributions and any derivative works thereof, under any
license — including but not limited to open source licenses and proprietary
commercial licenses.

You hereby grant to the Project Author a perpetual, worldwide, non-exclusive,
no-charge, royalty-free, irrevocable patent license to make, have made, use,
offer to sell, sell, import, and otherwise transfer your Contributions, where
such license applies only to patent claims licensable by you that are
necessarily infringed by your Contribution alone or by combination of your
Contribution with the project to which it was submitted.

### 3. Ownership and Retention of Rights

You retain all right, title, and interest in your Contributions. This agreement
does not transfer ownership of your Contributions — it grants the Project Author
a parallel license. You are free to use, license, or distribute your own
Contributions for any purpose.

### 4. Representations

You represent that:

(a) Each Contribution is your original creation, or you have sufficient rights
to submit it under these terms.

(b) Your Contribution does not violate any third party's intellectual property
rights, trade secrets, or other proprietary rights.

(c) You are legally entitled to grant the above licenses. If your employer has
rights to intellectual property that you create, you represent that you have
received permission to make Contributions on behalf of that employer, or that
your employer has waived such rights for your Contributions to this project.

(d) You understand that this project is dual-licensed and that your
Contributions may be included in versions of the project distributed under
the AGPL-3.0 license, under commercial proprietary licenses, or under any
other license chosen by the Project Author.

### 5. No Obligation

You understand that the decision to include your Contribution in the project
is entirely at the discretion of the Project Author. This agreement does not
obligate the Project Author to use, incorporate, or acknowledge any
Contribution.

### 6. Acceptance Mechanism

This CLA is accepted by the act of submitting a Contribution. No separate
signature is required. By submitting a pull request or other Contribution,
you confirm that you have read, understood, and agree to be bound by these
terms.

---

## How to Contribute

### Reporting Issues

- Open an issue on GitHub with a clear description
- Include steps to reproduce, expected behavior, and actual behavior
- For file format issues, note the file type (.dna, .gb, .fasta, etc.)

### Submitting Changes

1. Fork the repository
2. Create a feature branch from `main`
3. Make your changes with clear, small commits
4. Run the tests: `uv run pytest -v`
5. Submit a pull request against `main`

By submitting a pull request, you agree to the Contributor License Agreement
above.

### Development Setup

```bash
make setup
cp config/config.example.yaml config/config.local.yaml
export ZERG_CONFIG=config/config.local.yaml
make dev            # backend
make dev-frontend   # frontend (separate terminal)
```

### Adding a New Tool

The tool system is designed for easy extension:

1. Create `src/zerg/tools/mytool.py`:
   - Subclass `Tool`, set `name`, `description`, `widget_type`
   - Implement `input_schema()`, `execute()`, `format_result()`
   - Add a `create(config, llm_client)` factory function
2. Create `frontend/src/lib/MyToolWidget.svelte`
3. The tool is auto-discovered on startup — no registration needed

### Code Style

- **Python**: ruff (configured in pyproject.toml), line length 100
- **Frontend**: Svelte 5 runes (`$state`, `$derived`, `$effect`, `$props`)
- Keep changes focused — one concern per commit
- No unnecessary abstractions or premature optimization

### Testing

```bash
uv run pytest -v
```

Tests cover parsers, ingestion, and watcher rules. Add tests for new
functionality when reasonable.

## Code of Conduct

Be respectful and constructive. We're building tools for scientists — keep the
focus on making lab work easier.
