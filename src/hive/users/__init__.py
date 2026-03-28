"""User management — registration, auth, preferences, feedback."""

from hive.users.service import (
    create_feedback,
    create_user,
    feedback_stats,
    get_user_by_slug,
    get_user_by_token,
    list_feedback,
    list_users,
    make_slug,
    update_preferences,
    validate_username,
)

__all__ = [
    "create_feedback",
    "create_user",
    "feedback_stats",
    "get_user_by_slug",
    "get_user_by_token",
    "list_feedback",
    "list_users",
    "make_slug",
    "update_preferences",
    "validate_username",
]
