"""Chat storage — JSON file persistence on the server.

File naming: {chat_id}.json
Storage dir: configurable via config.chat.storage_dir.
No user field in MVP (no accounts).
"""

import json
import logging
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

logger = logging.getLogger(__name__)


class ChatStorage:
    """Persists chat sessions as JSON files in a server-side directory."""

    def __init__(self, storage_dir: str):
        self.storage_dir = Path(storage_dir).expanduser()
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def new_chat_id(self) -> str:
        ts = datetime.now(UTC).isoformat()
        return sha256(ts.encode()).hexdigest()[:8]

    def save(
        self,
        chat_id: str,
        messages: list[dict],
        title: str | None = None,
        created: datetime | None = None,
    ):
        if created is None:
            created = datetime.now(UTC)

        filepath = self.storage_dir / f"{chat_id}.json"

        # Preserve existing title/created if updating
        existing = self.load(chat_id)
        if existing:
            created = datetime.fromisoformat(existing["created"])
            if title is None:
                title = existing.get("title")

        data = {
            "id": chat_id,
            "title": title,
            "created": created.isoformat(),
            "messages": messages,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, chat_id: str) -> dict | None:
        filepath = self.storage_dir / f"{chat_id}.json"
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    def update_title(self, chat_id: str, title: str):
        data = self.load(chat_id)
        if data:
            data["title"] = title
            filepath = self.storage_dir / f"{chat_id}.json"
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)

    def delete(self, chat_id: str) -> bool:
        filepath = self.storage_dir / f"{chat_id}.json"
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_chats(self) -> list[dict]:
        chats = []
        for filepath in sorted(
            self.storage_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                chats.append({
                    "id": data["id"],
                    "title": data.get("title"),
                    "created": data["created"],
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed chat file: %s", filepath)
        return chats
