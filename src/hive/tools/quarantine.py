"""Tool quarantine — hash-based approval gate for external tools."""

from __future__ import annotations

import ast
import hashlib
import logging
from pathlib import Path

from sqlalchemy import select

from hive.db import session as db
from hive.db.models import ToolApproval

logger = logging.getLogger(__name__)


def compute_hash(path: Path) -> str:
    """SHA-256 hex digest of file contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_tool_name(source: str) -> str | None:
    """Find the 'name' class attribute of the first Tool subclass via AST."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for item in node.body:
            if (
                isinstance(item, ast.Assign)
                and len(item.targets) == 1
                and isinstance(item.targets[0], ast.Name)
                and item.targets[0].id == "name"
                and isinstance(item.value, (ast.Constant,))
                and isinstance(item.value.value, str)
            ):
                return item.value.value
    return None


async def sync_quarantine(tools_dir: str) -> set[str]:
    """Scan tools directory, sync with DB, return set of approved filenames.

    - New files -> quarantined
    - Approved + same hash -> approved set
    - Approved + changed hash -> re-quarantined
    - Quarantined/rejected -> skipped
    """
    tools_path = Path(tools_dir)
    approved: set[str] = set()

    if not tools_path.is_dir():
        return approved

    if not db.async_session_factory:
        logger.warning("No DB session — skipping external tools")
        return approved

    py_files = sorted(
        f for f in tools_path.glob("*.py") if not f.name.startswith("_")
    )

    if not py_files:
        return approved

    async with db.async_session_factory() as session:
        for py_file in py_files:
            filename = py_file.name
            file_hash = compute_hash(py_file)
            source = py_file.read_text()
            tool_name = extract_tool_name(source)

            record = (
                await session.execute(
                    select(ToolApproval).where(ToolApproval.filename == filename)
                )
            ).scalar_one_or_none()

            if record is None:
                # New tool — quarantine
                session.add(ToolApproval(
                    filename=filename,
                    file_hash=file_hash,
                    tool_name=tool_name,
                    status="quarantined",
                ))
                logger.warning("Quarantined new tool: %s", filename)
            elif record.status == "approved":
                if record.file_hash == file_hash:
                    approved.add(filename)
                else:
                    # Content changed — re-quarantine
                    record.file_hash = file_hash
                    record.tool_name = tool_name
                    record.status = "quarantined"
                    record.reviewed_at = None
                    logger.warning(
                        "Re-quarantined modified tool: %s", filename
                    )
            else:
                logger.info(
                    "Skipping %s tool: %s", record.status, filename
                )

        await session.commit()

    return approved
