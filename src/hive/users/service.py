"""User service — create, lookup, list, and manage user preferences."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import User

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9\-_ ]+$")
_MAX_USERNAME_LEN = 50


def make_slug(username: str) -> str:
    """Convert display name to slug: strip hyphens/underscores/spaces, lowercase."""
    return re.sub(r"[\-_ ]", "", username).lower()


def validate_username(username: str) -> bool:
    """Check username matches allowed chars and length."""
    return bool(username) and len(username) <= _MAX_USERNAME_LEN and bool(_USERNAME_RE.match(username))


async def create_user(session: AsyncSession, username: str) -> User:
    """Create a new user. Raises ValueError on invalid/duplicate username."""
    if not validate_username(username):
        raise ValueError("Invalid username: ASCII letters, digits, hyphens, underscores, and spaces only (1-50 chars)")

    slug = make_slug(username)
    if not slug:
        raise ValueError("Username must contain at least one alphanumeric character")

    existing = (await session.execute(select(User).where(User.slug == slug))).scalar_one_or_none()
    if existing:
        raise ValueError(f"Username already taken (slug: {slug})")

    token = secrets.token_urlsafe(32)
    user = User(username=username, slug=slug, token=token, preferences={})
    session.add(user)
    await session.flush()
    return user


async def get_user_by_token(session: AsyncSession, token: str) -> User | None:
    """Look up user by auth token."""
    return (await session.execute(select(User).where(User.token == token))).scalar_one_or_none()


async def list_users(session: AsyncSession) -> list[User]:
    """Return all users ordered by creation date."""
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


async def update_preferences(session: AsyncSession, user_id: int, key: str, value) -> dict:
    """Merge a key into the user's preferences JSON. Returns updated preferences."""
    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    prefs = dict(user.preferences) if user.preferences else {}
    prefs[key] = value
    user.preferences = prefs
    await session.commit()
    return prefs
