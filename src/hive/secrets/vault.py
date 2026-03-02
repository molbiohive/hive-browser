"""SecretVault -- manages opaque references to protected data.

Consumers register sensitive values (sequences, credentials, paths)
and receive opaque tokens. The LLM sees tokens; tools resolve them
back to real values transparently.

Scoped per-request (router loop) or per-session (future sandbox).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Any

# Keys that are always treated as sensitive regardless of value length
SENSITIVE_KEYS = {"sequence", "raw_sequence", "file_path", "path", "file_name", "filename"}


@dataclass
class SecretEntry:
    value: str
    kind: str
    meta: dict = field(default_factory=dict)


class SecretVault:
    """Manages opaque references to protected data."""

    def __init__(self) -> None:
        self._store: dict[str, SecretEntry] = {}  # token -> entry
        self._dedup: dict[int, str] = {}           # hash -> token

    def register(
        self, value: str, kind: str = "sequence", meta: dict | None = None,
    ) -> str:
        """Store a value, return an opaque token like SEC:a3f2b1c0.

        kind: "sequence", "path", "name" -- for auditing/filtering.
        meta: optional metadata (molecule, length) shown to LLM instead of value.
        Deduplicates: same value -> same token.
        """
        h = hash(value)
        if h in self._dedup:
            return self._dedup[h]
        token = f"SEC:{secrets.token_hex(4)}"
        self._store[token] = SecretEntry(value=value, kind=kind, meta=meta or {})
        self._dedup[h] = token
        return token

    def resolve(self, token: str) -> str | None:
        """Resolve a token back to its value. Returns None if not found."""
        entry = self._store.get(token)
        return entry.value if entry else None

    def resolve_or_passthrough(self, value: str) -> str:
        """If value is a SEC: token, resolve it. Otherwise return as-is."""
        if isinstance(value, str) and value.startswith("SEC:"):
            return self.resolve(value) or value
        return value

    def describe(self, token: str) -> str:
        """LLM-safe description: token + metadata, no actual value."""
        entry = self._store.get(token)
        if not entry:
            return token
        parts = [token]
        if m := entry.meta:
            if mol := m.get("molecule"):
                parts.append(mol)
            if length := m.get("length"):
                parts.append(f"{length}bp")
        return f"({', '.join(parts)})"

    def scan_and_protect(
        self, result: dict[str, Any], min_length: int = 200,
    ) -> dict[str, Any]:
        """Scan a result dict, replace long strings with tokens.

        Returns a NEW dict (original untouched) for LLM context.
        Keys matching SENSITIVE_KEYS are always protected.
        Other string values are protected only if longer than min_length.
        """
        protected: dict[str, Any] = {}
        for key, value in result.items():
            if isinstance(value, str):
                if key in SENSITIVE_KEYS or len(value) >= min_length:
                    kind = "sequence" if key in {"sequence", "raw_sequence"} else "data"
                    meta: dict[str, Any] = {}
                    if key in {"sequence", "raw_sequence"}:
                        meta["length"] = len(value)
                    protected[key] = self.register(value, kind=kind, meta=meta)
                else:
                    protected[key] = value
            elif isinstance(value, list):
                protected[key] = [
                    self._protect_item(item, min_length) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            elif isinstance(value, dict):
                protected[key] = self._protect_item(value, min_length)
            else:
                protected[key] = value
        return protected

    def _protect_item(self, item: dict, min_length: int) -> dict:
        """Protect sensitive fields in a nested dict."""
        out: dict[str, Any] = {}
        for k, v in item.items():
            if isinstance(v, str) and (k in SENSITIVE_KEYS or len(v) >= min_length):
                kind = "sequence" if k in {"sequence", "raw_sequence"} else "data"
                out[k] = self.register(v, kind=kind)
            else:
                out[k] = v
        return out

    def scan_and_resolve(self, params: dict[str, Any]) -> dict[str, Any]:
        """Scan tool params, resolve any SEC: tokens back to values."""
        resolved: dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str) and value.startswith("SEC:"):
                resolved[key] = self.resolve(value) or value
            else:
                resolved[key] = value
        return resolved

    def __len__(self) -> int:
        return len(self._store)
