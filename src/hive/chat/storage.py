"""Chat storage — JSON file persistence on the server.

File naming: {user_slug}-{chat_id}.json (or {chat_id}.json without user).
Storage dir: configurable via config.chat.storage_dir.
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
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _filepath(self, chat_id: str, user_slug: str | None = None) -> Path:
        if user_slug:
            return self.storage_dir / f"{user_slug}-{chat_id}.json"
        return self.storage_dir / f"{chat_id}.json"

    def new_chat_id(self) -> str:
        ts = datetime.now(UTC).isoformat()
        return sha256(ts.encode()).hexdigest()[:8]

    def save(
        self,
        chat_id: str,
        messages: list[dict],
        user_slug: str | None = None,
        title: str | None = None,
        created: datetime | None = None,
        model: str | None = None,
    ):
        if created is None:
            created = datetime.now(UTC)

        filepath = self._filepath(chat_id, user_slug)

        # Preserve existing title/created/model if updating
        existing = self.load(chat_id, user_slug)
        if existing:
            created = datetime.fromisoformat(existing["created"])
            if title is None:
                title = existing.get("title")
            if model is None:
                model = existing.get("model")

        data = {
            "id": chat_id,
            "title": title,
            "created": created.isoformat(),
            "model": model,
            "messages": messages,
        }

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

    def load(self, chat_id: str, user_slug: str | None = None) -> dict | None:
        filepath = self._filepath(chat_id, user_slug)
        if filepath.exists():
            with open(filepath) as f:
                return json.load(f)
        return None

    def update_title(self, chat_id: str, title: str, user_slug: str | None = None):
        data = self.load(chat_id, user_slug)
        if data:
            data["title"] = title
            filepath = self._filepath(chat_id, user_slug)
            with open(filepath, "w") as f:
                json.dump(data, f, indent=2, default=str)

    def delete(self, chat_id: str, user_slug: str | None = None) -> bool:
        filepath = self._filepath(chat_id, user_slug)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def list_chats(self, user_slug: str | None = None) -> list[dict]:
        if user_slug:
            pattern = f"{user_slug}-*.json"
            prefix_len = len(user_slug) + 1  # slug + hyphen
        else:
            pattern = "*.json"
            prefix_len = 0

        chats = []
        for filepath in sorted(
            self.storage_dir.glob(pattern),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                chat_id = filepath.stem[prefix_len:] if prefix_len else filepath.stem
                chats.append({
                    "id": chat_id,
                    "title": data.get("title"),
                    "created": data["created"],
                    "message_count": len(data.get("messages", [])),
                })
            except (json.JSONDecodeError, KeyError):
                logger.warning("Skipping malformed chat file: %s", filepath)
        return chats
