"""Admin CLI — talk to a running Hive server."""

import argparse
import asyncio
import json
import sys

import httpx

from hive.admin.token import HIVE_HOME, load_token

DEFAULT_URL = "http://localhost:8080"


def _client(args) -> tuple[httpx.Client, dict]:
    """Build HTTP client and auth headers."""
    token = args.token or load_token()
    if not token:
        print(f"No admin token found. Check {HIVE_HOME / 'admin.token'}", file=sys.stderr)
        sys.exit(1)
    headers = {"Authorization": f"Bearer {token}"}
    return httpx.Client(base_url=args.url, timeout=30), headers


def _request(client, method, path, headers):
    try:
        r = getattr(client, method)(path, headers=headers)
    except httpx.ConnectError:
        print(f"Cannot connect to {client.base_url}", file=sys.stderr)
        sys.exit(1)
    if r.status_code == 401:
        print("Invalid admin token", file=sys.stderr)
        sys.exit(1)
    if r.status_code == 503:
        detail = r.json().get("detail", "Service unavailable")
        print(f"Server: {detail}", file=sys.stderr)
        sys.exit(1)
    r.raise_for_status()
    return r.json()


def _get(args, path: str):
    client, headers = _client(args)
    return _request(client, "get", path, headers)


def _post(args, path: str):
    client, headers = _client(args)
    return _request(client, "post", path, headers)


def _pp(data):
    """Pretty-print JSON."""
    print(json.dumps(data, indent=2))


# ── Commands ─────────────────────────────────────────────────────────


def cmd_health(args):
    _pp(_get(args, "/admin/health"))


def cmd_status(args):
    _pp(_get(args, "/admin/status"))


def cmd_watcher_start(args):
    _pp(_post(args, "/admin/watcher/start"))


def cmd_watcher_stop(args):
    _pp(_post(args, "/admin/watcher/stop"))


def cmd_watcher_rescan(args):
    _pp(_post(args, "/admin/watcher/rescan"))


def cmd_files(args):
    data = _get(args, "/admin/db/files")
    files = data.get("files", [])
    if not files:
        print("No indexed files.")
        return
    for f in files:
        status = f["status"]
        marker = "+" if status == "active" else ("x" if status == "error" else "-")
        size_kb = f["size"] / 1024 if f["size"] else 0
        print(f"  [{marker}] {f['path']}  ({f['format']}, {size_kb:.1f} KB)")


def cmd_errors(args):
    data = _get(args, "/admin/db/errors")
    errors = data.get("errors", [])
    if not errors:
        print("No parse errors.")
        return
    for e in errors:
        print(f"  {e['path']}")
        print(f"    {e['error']}")


def cmd_token(args):
    """Show the current admin token."""
    token = load_token()
    if token:
        print(token)
    else:
        print(f"No token found at {HIVE_HOME / 'admin.token'}", file=sys.stderr)
        sys.exit(1)


# ── User commands (direct DB, no server needed) ─────────────────────


def _db_url():
    """Resolve database URL from config."""
    from hive.config import load_config

    return load_config().database.url


async def _run_user_cmd(coro_fn):
    """Init async DB and run a coroutine."""
    from hive.db import session as db

    await db.init_db(type("C", (), {"url": _db_url()})())
    async with db.async_session_factory() as s:
        await coro_fn(s)


def cmd_users(args):
    """List all users."""
    async def _list(s):
        from hive.users.service import list_users

        users = await list_users(s)
        if not users:
            print("No users.")
            return
        for u in users:
            print(f"  {u.id:3d}  {u.slug:<20s}  {u.username}")

    asyncio.run(_run_user_cmd(_list))


def cmd_user_add(args):
    """Create a new user."""
    async def _add(s):
        from hive.users.service import create_user

        try:
            user = await create_user(s, args.username)
            await s.commit()
            print(f"Created user: {user.username} (slug: {user.slug})")
            print(f"Token: {user.token}")
        except ValueError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

    asyncio.run(_run_user_cmd(_add))


def cmd_user_rm(args):
    """Remove a user by slug."""
    async def _rm(s):
        from sqlalchemy import delete

        from hive.db.models import User

        result = await s.execute(
            delete(User).where(User.slug == args.slug)
        )
        await s.commit()
        if result.rowcount:
            print(f"Deleted user: {args.slug}")
        else:
            print(f"User not found: {args.slug}", file=sys.stderr)
            sys.exit(1)

    asyncio.run(_run_user_cmd(_rm))


def cmd_user_edit(args):
    """Edit a user's username."""
    async def _edit(s):
        from hive.users.service import get_user_by_slug, make_slug

        user = await get_user_by_slug(s, args.slug)
        if not user:
            print(f"User not found: {args.slug}", file=sys.stderr)
            sys.exit(1)
        old_name = user.username
        user.username = args.new_name
        user.slug = make_slug(args.new_name)
        await s.commit()
        print(f"Renamed: {old_name} -> {user.username} (slug: {user.slug})")

    asyncio.run(_run_user_cmd(_edit))


# ── Entry point ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="hive-admin",
        description="Admin CLI for Hive Browser server",
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help=f"Server URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--token", default=None,
        help="Admin token (default: read from ~/.hive/admin.token)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("health", help="Server health check")
    sub.add_parser("status", help="System status (DB counts, watcher state)")
    sub.add_parser("token", help="Show current admin token")

    # Watcher
    sub.add_parser("watcher-start", help="Start the file watcher")
    sub.add_parser("watcher-stop", help="Stop the file watcher")
    sub.add_parser("watcher-rescan", help="Force full directory rescan")

    # Database
    sub.add_parser("files", help="List indexed files")
    sub.add_parser("errors", help="List parse errors")

    # Users (direct DB — no server needed)
    sub.add_parser("users", help="List all users")
    p_add = sub.add_parser("user-add", help="Create a new user")
    p_add.add_argument("username", help="Display name for the new user")
    p_rm = sub.add_parser("user-rm", help="Remove a user by slug")
    p_rm.add_argument("slug", help="User slug to remove")
    p_edit = sub.add_parser("user-edit", help="Rename a user")
    p_edit.add_argument("slug", help="Current user slug")
    p_edit.add_argument("new_name", help="New display name")

    args = parser.parse_args()

    dispatch = {
        "health": cmd_health,
        "status": cmd_status,
        "token": cmd_token,
        "watcher-start": cmd_watcher_start,
        "watcher-stop": cmd_watcher_stop,
        "watcher-rescan": cmd_watcher_rescan,
        "files": cmd_files,
        "errors": cmd_errors,
        "users": cmd_users,
        "user-add": cmd_user_add,
        "user-rm": cmd_user_rm,
        "user-edit": cmd_user_edit,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
