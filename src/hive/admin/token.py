"""Admin token management — generate, save, load."""

import logging
import secrets
from pathlib import Path

logger = logging.getLogger(__name__)

HIVE_HOME = Path.home() / ".hive"
TOKEN_FILENAME = "admin.token"


def generate_token() -> str:
    """Generate a cryptographically secure admin token."""
    return secrets.token_urlsafe(32)


def save_token(token: str, token_dir: Path | None = None) -> Path:
    """Save admin token to disk. Returns the file path."""
    d = token_dir or HIVE_HOME
    d.mkdir(parents=True, exist_ok=True)
    path = d / TOKEN_FILENAME
    path.write_text(token)
    path.chmod(0o600)
    logger.info("Admin token saved to %s", path)
    return path


def load_token(token_dir: Path | None = None) -> str | None:
    """Load admin token from disk. Returns None if not found."""
    d = token_dir or HIVE_HOME
    path = d / TOKEN_FILENAME
    if path.exists():
        return path.read_text().strip()
    return None
