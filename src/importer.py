import os
from pathlib import Path
from datetime import datetime


class Importer:
    def __init__(self, db):
        self.db = db

    async def scan_directory(self, path: str, recursive: bool = True):
        directory = Path(path)
        if not directory.exists():
            return {"error": f"Path {path} does not exist", "imported": 0}

        pattern = "**/*" if recursive else "*"
        files = [f for f in directory.glob(pattern) if f.is_file()]

        imported = 0
        for file_path in files:
            if file_path.suffix.lower() in [".fasta", ".fa", ".txt"]:
                entry = self.parse_file(str(file_path))
                await self.db.insert(entry)
                imported += 1

        return {"imported": imported, "total": len(files)}

    def parse_file(self, file_path: str) -> dict:
        entry = {
            "file_path": file_path,
            "file_type": Path(file_path).suffix,
            "data_type": "dna",
            "sequences": [],
            "features": [],
            "primers": [],
            "names": [],
            "indexed_at": datetime.now().isoformat(),
        }

        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Basic FASTA parsing
            if entry["file_type"] in [".fasta", ".fa"]:
                sequences, names = [], []
                current_seq, current_name = "", ""

                for line in content.split("\n"):
                    if line.startswith(">"):
                        if current_seq:
                            sequences.append(current_seq)
                            names.append(current_name)
                        current_name = line[1:].strip()
                        current_seq = ""
                    else:
                        current_seq += line.strip()

                if current_seq:
                    sequences.append(current_seq)
                    names.append(current_name)

                entry["sequences"] = sequences
                entry["names"] = names

                # Detect type
                if sequences and "U" in sequences[0].upper():
                    entry["data_type"] = "rna"
                elif sequences and any(aa in sequences[0].upper() for aa in "EFILPQ"):
                    entry["data_type"] = "protein"

                # Find features
                for keyword in ["promoter", "gene", "exon", "intron", "UTR"]:
                    if keyword.lower() in content.lower():
                        entry["features"].append(keyword)

                # Find primers (15-30bp sequences)
                entry["primers"] = [s for s in sequences if 15 <= len(s) <= 30]

        except Exception as e:
            entry["error"] = str(e)

        return entry
