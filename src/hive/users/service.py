"""User service — create, lookup, list, and manage user preferences."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from hive.db.models import Feedback, User

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9\-_ ]+$")
_MAX_USERNAME_LEN = 50


def make_slug(username: str) -> str:
    """Convert display name to slug: strip hyphens/underscores/spaces, lowercase."""
    return re.sub(r"[\-_ ]", "", username).lower()


def validate_username(username: str) -> bool:
    """Check username matches allowed chars and length."""
    return (
        bool(username)
        and len(username) <= _MAX_USERNAME_LEN
        and bool(_USERNAME_RE.match(username))
    )


async def create_user(session: AsyncSession, username: str) -> User:
    """Create a new user. Raises ValueError on invalid/duplicate username."""
    if not validate_username(username):
        raise ValueError(
            "Invalid username: ASCII letters, digits, hyphens,"
            " underscores, and spaces only (1-50 chars)"
        )

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


async def get_user_by_slug(session: AsyncSession, slug: str) -> User | None:
    """Look up user by slug (for passwordless local login)."""
    return (await session.execute(select(User).where(User.slug == slug))).scalar_one_or_none()


async def list_users(session: AsyncSession) -> list[User]:
    """Return all users ordered by creation date."""
    result = await session.execute(select(User).order_by(User.created_at))
    return list(result.scalars().all())


_ALLOWED_PREF_KEYS = {"theme", "model_id"}


async def update_preferences(session: AsyncSession, user_id: int, key: str, value) -> dict:
    """Merge a key into the user's preferences JSON. Returns updated preferences."""
    if key not in _ALLOWED_PREF_KEYS:
        raise ValueError(f"Unknown preference key: {key}")

    user = (await session.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if not user:
        raise ValueError(f"User {user_id} not found")

    prefs = dict(user.preferences) if user.preferences else {}
    prefs[key] = value
    user.preferences = prefs
    await session.commit()
    return prefs


# -- Feedback --


async def create_feedback(
    session: AsyncSession,
    user_id: int,
    rating: str,
    priority: int,
    comment: str,
    chat_id: str | None = None,
) -> Feedback:
    """Store a feedback entry."""
    fb = Feedback(
        user_id=user_id,
        chat_id=chat_id,
        rating=rating,
        priority=max(1, min(5, priority)),
        comment=comment,
    )
    session.add(fb)
    await session.commit()
    return fb


async def list_feedback(session: AsyncSession) -> list[Feedback]:
    """Return all feedback ordered by newest first, with user eagerly loaded."""
    from sqlalchemy.orm import selectinload

    result = await session.execute(
        select(Feedback)
        .options(selectinload(Feedback.user))
        .order_by(Feedback.created_at.desc())
    )
    return list(result.scalars().all())


async def feedback_stats(session: AsyncSession) -> dict:
    """Return feedback summary stats."""
    from sqlalchemy import func as sqlfunc

    rows = (await session.execute(
        select(Feedback.rating, sqlfunc.count()).group_by(Feedback.rating)
    )).all()

    counts = {r: c for r, c in rows}
    total = sum(counts.values())
    good = counts.get("good", 0)
    bad = counts.get("bad", 0)

    last = (await session.execute(
        select(Feedback.created_at, User.username)
        .join(User, Feedback.user_id == User.id)
        .order_by(Feedback.created_at.desc())
        .limit(1)
    )).first()

    return {
        "total": total,
        "good": good,
        "bad": bad,
        "last_at": last[0].isoformat() if last else None,
        "last_by": last[1] if last else None,
    }
