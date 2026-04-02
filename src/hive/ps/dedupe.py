"""Dedupe process -- remove duplicate indexed files in background."""

from __future__ import annotations

import logging

from hive.admin.db import dedupe
from hive.db import session as db
from hive.ps.base import Process, ProcessContext
from hive.utils import timed

logger = logging.getLogger(__name__)


class DedupeProcess(Process):
    """Remove duplicate indexed files."""

    name = "dedupe"
    description = "Remove duplicate indexed files"

    async def run(self, ctx: ProcessContext) -> str:
        if not db.async_session_factory:
            return "Database unavailable"
        with timed() as t:
            async with db.async_session_factory() as session:
                result = await dedupe(session, dry_run=False)
        return f"{result['removed']} duplicates removed in {t}"
