"""BLAST+ dependency — subprocess wrappers for all BLAST programs."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from hive.db import session as db
from hive.db.models import IndexedFile, Sequence
from hive.deps import Dep

logger = logging.getLogger(__name__)

# Program -> database type mapping
PROGRAM_DB = {
    "blastn": "nucl",
    "blastp": "prot",
    "blastx": "prot",
    "tblastn": "nucl",
    "tblastx": "nucl",
}

# Database type -> index file extension (used to check if DB exists)
DB_EXT = {"nucl": ".ndb", "prot": ".pdb"}


class BlastDep(Dep):
    """BLAST+ external dependency — index building and sequence search."""

    name = "blast"
    needs_rebuild_on_ingest = True

    def __init__(self, data_dir: str, bin_dir: str = ""):
        self._data_dir = data_dir
        self._bin_dir = bin_dir

    def resolve_binary(self, program: str) -> str:
        if self._bin_dir:
            return str(Path(self._bin_dir) / program)
        return program

    async def health(self) -> dict[str, Any]:
        binary = self.resolve_binary("blastn")
        try:
            rc, stdout, _ = await self._run([binary, "-version"])
            if rc == 0:
                version = stdout.decode().strip().split("\n")[0]
                return {"ok": True, "version": version}
        except FileNotFoundError:
            pass
        return {"ok": False, "version": None}

    async def setup(self) -> bool:
        return await self.build_index()

    async def build_index(self) -> bool:
        """Build BLAST databases (nucleotide + protein) from all active sequences.

        Called on startup and after watcher changes.  Uses a lockfile
        to prevent races when multiple workers start simultaneously.
        """
        if not db.async_session_factory:
            logger.warning("Cannot build BLAST index: database unavailable")
            return False

        blast_dir = Path(self._data_dir).expanduser()
        blast_dir.mkdir(parents=True, exist_ok=True)
        lock_file = blast_dir / ".build.lock"

        # Clean up stale lockfile (older than 10 minutes)
        if lock_file.exists():
            age = time.time() - lock_file.stat().st_mtime
            if age > 600:
                logger.warning("Removing stale BLAST lock (%.0fs old)", age)
                lock_file.unlink(missing_ok=True)

        # Skip if another worker is already building
        try:
            fd = lock_file.open("x")  # atomic create -- fails if exists
        except FileExistsError:
            logger.info("BLAST index build already in progress, skipping")
            return True
        try:
            return await self._do_build_index(blast_dir)
        finally:
            fd.close()
            lock_file.unlink(missing_ok=True)

    async def _do_build_index(self, blast_dir: Path) -> bool:
        # Remove stale index files before rebuilding
        for old in blast_dir.glob("hive_nucl.*"):
            old.unlink()
        for old in blast_dir.glob("hive_prot.*"):
            old.unlink()

        async with db.async_session_factory() as session:
            rows = (await session.execute(
                select(Sequence.name, Sequence.sequence, Sequence.molecule)
                .join(IndexedFile, Sequence.file_id == IndexedFile.id)
                .where(IndexedFile.status == "active")
            )).all()

        if not rows:
            logger.info("No sequences to index for BLAST")
            return False

        # Split sequences by type
        nucl_fasta = blast_dir / "nucl_sequences.fasta"
        prot_fasta = blast_dir / "prot_sequences.fasta"
        nucl_count = 0
        prot_count = 0

        with open(nucl_fasta, "w") as nf, open(prot_fasta, "w") as pf:
            for name, seq, molecule in rows:
                safe_name = name.replace(" ", "_")
                if molecule == "protein":
                    pf.write(f">{safe_name}\n{seq}\n")
                    prot_count += 1
                else:
                    nucl_seq = seq.replace("U", "T").replace("u", "t") if molecule == "RNA" else seq
                    nf.write(f">{safe_name}\n{nucl_seq}\n")
                    nucl_count += 1

        makeblastdb = self.resolve_binary("makeblastdb")
        ok = True

        # Build nucleotide DB
        if nucl_count > 0:
            ok = await self._run_makeblastdb(makeblastdb, nucl_fasta, blast_dir / "hive_nucl", "nucl") and ok
            logger.info("BLAST nucl index: %d sequences", nucl_count)
        else:
            logger.info("No nucleotide sequences to index for BLAST")

        # Build protein DB
        if prot_count > 0:
            ok = await self._run_makeblastdb(makeblastdb, prot_fasta, blast_dir / "hive_prot", "prot") and ok
            logger.info("BLAST prot index: %d sequences", prot_count)

        return ok

    async def _run_makeblastdb(self, binary: str, fasta: Path, db_file: Path, dbtype: str) -> bool:
        proc = await asyncio.create_subprocess_exec(
            binary,
            "-in", str(fasta),
            "-dbtype", dbtype,
            "-out", str(db_file),
            "-blastdb_version", "5",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("makeblastdb (%s) failed: %s", dbtype, stderr.decode())
            return False
        return True

    async def run_search(
        self,
        program: str,
        query_seq: str,
        db_path: Path,
        **params: Any,
    ) -> dict[str, Any]:
        """Run a BLAST+ program and return parsed hits.

        Accepts any BLAST CLI parameters as kwargs (None values are skipped).
        Returns {"hits": [...], "subject_names": set, "query_length": int, "error": str|None}.
        """
        db_type = PROGRAM_DB.get(program)
        if not db_type:
            return {"error": f"Unknown BLAST program: {program}", "hits": []}

        db_file = db_path / f"hive_{db_type}"
        ext = DB_EXT[db_type]
        if not (db_path / f"hive_{db_type}{ext}").exists():
            return {"error": f"BLAST {db_type} index not built yet", "hits": []}

        # Write query to temp FASTA
        with tempfile.NamedTemporaryFile(mode="w", suffix=".fasta", delete=False) as f:
            f.write(f">query\n{query_seq}\n")
            query_file = f.name

        binary = self.resolve_binary(program)
        cmd = [
            binary,
            "-query", query_file,
            "-db", str(db_file),
            "-outfmt",
            "6 sseqid pident length mismatch gapopen "
            "qstart qend sstart send evalue bitscore",
        ]

        # Block params that override I/O, output format, or leak data externally
        blocked = {
            "outfmt", "out", "query", "db", "remote", "html",
            "import_search_strategy", "export_search_strategy",
            "gilist", "negative_gilist", "seqidlist", "negative_seqidlist",
            "entrez_query", "blastdb_version",
        }
        for key, value in params.items():
            if value is None or key in blocked:
                continue
            flag = f"-{key}"
            if isinstance(value, bool):
                if value:
                    cmd.append(flag)
            else:
                cmd.extend([flag, str(value)])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
        finally:
            Path(query_file).unlink(missing_ok=True)

        if proc.returncode != 0:
            err = stderr.decode().strip()
            logger.error("BLAST failed (%s): %s", program, err)
            return {"error": f"BLAST error: {err}", "hits": []}

        hits = []
        subject_names: set[str] = set()
        for line in stdout.decode().strip().split("\n"):
            if not line:
                continue
            parts = line.split("\t")
            if len(parts) < 11:
                continue
            subject_name = parts[0]
            subject_names.add(subject_name)
            hits.append({
                "subject": subject_name,
                "identity": float(parts[1]),
                "alignment_length": int(parts[2]),
                "mismatches": int(parts[3]),
                "gaps": int(parts[4]),
                "q_start": int(parts[5]),
                "q_end": int(parts[6]),
                "s_start": int(parts[7]),
                "s_end": int(parts[8]),
                "evalue": float(parts[9]),
                "bitscore": float(parts[10]),
            })

        return {
            "hits": hits,
            "subject_names": subject_names,
            "query_length": len(query_seq),
        }
