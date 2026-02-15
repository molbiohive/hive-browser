"""Chat storage — JSON file persistence on the server.

File naming: {hash}-{date}.json
Storage dir: configurable via ZERG_CHAT_DIR env var.
No user field in MVP (no accounts).
Only tool + params stored in widgets (no cached data).
"""

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

logger = logging.getLogger(__name__)


def _chat_filename(chat_id: str, created: datetime) -> str:
    return f"{chat_id}-{created.strftime('%Y-%m-%d')}.json"


class ChatStorage:
    """Persists chat sessions as JSON files in a server-side directory."""

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def new_chat_id(self) -> str:
        ts = datetime.now(timezone.utc).isoformat()
        return sha256(ts.encode()).hexdigest()[:8]

    def save(self, chat_id: str, messages: list[dict], created: datetime | None = None):
        if created is None:
            created = datetime.now(timezone.utc)

        filepath = self.storage_dir / _chat_filename(chat_id, created)

        data = {
            "id": chat_id,
            "created": created.isoformat(),
            "messages": messages,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, chat_id: str) -> dict | None:
        for filepath in self.storage_dir.glob(f"{chat_id}-*.json"):
            with open(filepath) as f:
                return json.load(f)
        return None

    def list_chats(self) -> list[dict]:
        chats = []
        for filepath in sorted(self.storage_dir.glob("*.json"), reverse=True):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                chats.append({
                    "id": data["id"],
                    "created": data["created"],
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed chat file: %s", filepath)
        return chats
