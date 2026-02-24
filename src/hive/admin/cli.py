"""Admin CLI — talk to a running Hive server."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

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


def cmd_watcher_reindex(args):
    _pp(_post(args, "/admin/watcher/reindex"))


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


# ── Feedback commands (direct DB, no server needed) ──────────────────


def cmd_feedback_stats(args):
    """Show feedback summary."""
    async def _stats(s):
        from hive.users.service import feedback_stats

        st = await feedback_stats(s)
        total = st["total"]
        if not total:
            print("No feedback yet.")
            return
        good = st["good"]
        bad = st["bad"]
        good_pct = good * 100 // total if total else 0
        bad_pct = bad * 100 // total if total else 0
        print("Feedback stats:")
        print(f"  Total: {total}")
        print(f"  Good:  {good} ({good_pct}%)")
        print(f"  Bad:   {bad} ({bad_pct}%)")
        if st["last_at"]:
            print(f"  Last:  {st['last_at']} by {st['last_by']}")

    asyncio.run(_run_user_cmd(_stats))


def cmd_feedback_report(args):
    """Generate feedback report as markdown file."""
    async def _report(s):
        from hive.users.service import feedback_stats, list_feedback

        items = await list_feedback(s)
        if not items:
            print("No feedback to report.")
            return

        st = await feedback_stats(s)
        from datetime import datetime, UTC

        lines = [
            "# Hive Browser Feedback Report",
            "",
            f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Summary",
            f"- Total: {st['total']} | Good: {st['good']} | Bad: {st['bad']}",
            "",
            "## Feedback",
            "",
            "| # | Date | User | Rating | Priority | Comment |",
            "|---|------|------|--------|----------|---------|",
        ]
        for i, fb in enumerate(items, 1):
            date = fb.created_at.strftime("%Y-%m-%d %H:%M") if fb.created_at else ""
            username = fb.user.username if fb.user else "unknown"
            comment = fb.comment.replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| {i} | {date} | {username} | {fb.rating} | {fb.priority} | {comment} |"
            )

        out = args.output if hasattr(args, "output") and args.output else "feedback_report.md"
        with open(out, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Report written to {out} ({len(items)} entries)")

    asyncio.run(_run_user_cmd(_report))


# ── Tool quarantine commands (direct DB, no server needed) ───────────


def cmd_tool_list(args):
    """List external tools and their approval status."""
    async def _list(s):
        from sqlalchemy import select as sel

        from hive.db.models import ToolApproval

        rows = (await s.execute(
            sel(ToolApproval).order_by(ToolApproval.created_at)
        )).scalars().all()
        if not rows:
            print("No external tools registered.")
            return
        for t in rows:
            name = t.tool_name or "?"
            short_hash = t.file_hash[:8]
            date = t.created_at.strftime("%Y-%m-%d") if t.created_at else ""
            print(f"  {t.status:<13s} {t.filename:<30s} {name:<20s} {short_hash}  {date}")

    asyncio.run(_run_user_cmd(_list))


def cmd_tool_approve(args):
    """Approve a quarantined tool."""
    async def _approve(s):
        from sqlalchemy import select as sel

        from hive.db.models import ToolApproval

        record = (await s.execute(
            sel(ToolApproval).where(ToolApproval.filename == args.filename)
        )).scalar_one_or_none()
        if not record:
            print(f"Tool not found: {args.filename}", file=sys.stderr)
            sys.exit(1)
        if record.status == "approved":
            print(f"Already approved: {args.filename}")
            return

        from datetime import UTC, datetime

        record.status = "approved"
        record.reviewed_at = datetime.now(UTC)
        await s.commit()
        print(f"Approved: {args.filename}")
        print("Restart the server to load this tool.")

    asyncio.run(_run_user_cmd(_approve))


def cmd_tool_reject(args):
    """Reject a quarantined tool."""
    async def _reject(s):
        from sqlalchemy import select as sel

        from hive.db.models import ToolApproval

        record = (await s.execute(
            sel(ToolApproval).where(ToolApproval.filename == args.filename)
        )).scalar_one_or_none()
        if not record:
            print(f"Tool not found: {args.filename}", file=sys.stderr)
            sys.exit(1)

        from datetime import UTC, datetime

        record.status = "rejected"
        record.reviewed_at = datetime.now(UTC)
        await s.commit()
        print(f"Rejected: {args.filename}")

    asyncio.run(_run_user_cmd(_reject))


def cmd_tool_show(args):
    """Show source code of an external tool for review."""
    from hive.config import load_config

    tools_dir = Path(load_config().tools_dir)
    tool_file = tools_dir / args.filename
    if not tool_file.is_file():
        print(f"File not found: {tool_file}", file=sys.stderr)
        sys.exit(1)
    print(tool_file.read_text())


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
    sub.add_parser("watcher-reindex", help="Re-parse all files (reset hashes and rescan)")

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

    # Feedback (direct DB — no server needed)
    sub.add_parser("feedback-stats", help="Show feedback summary")
    p_report = sub.add_parser("feedback-report", help="Generate feedback report (.md)")
    p_report.add_argument("-o", "--output", default="feedback_report.md", help="Output file")

    # Tool quarantine (direct DB — no server needed)
    sub.add_parser("tool-list", help="List external tools and approval status")
    p_tapprove = sub.add_parser("tool-approve", help="Approve a quarantined tool")
    p_tapprove.add_argument("filename", help="Tool filename (e.g. my_tool.py)")
    p_treject = sub.add_parser("tool-reject", help="Reject a quarantined tool")
    p_treject.add_argument("filename", help="Tool filename (e.g. my_tool.py)")
    p_tshow = sub.add_parser("tool-show", help="Show tool source code for review")
    p_tshow.add_argument("filename", help="Tool filename (e.g. my_tool.py)")

    args = parser.parse_args()

    dispatch = {
        "health": cmd_health,
        "status": cmd_status,
        "token": cmd_token,
        "watcher-start": cmd_watcher_start,
        "watcher-stop": cmd_watcher_stop,
        "watcher-rescan": cmd_watcher_rescan,
        "watcher-reindex": cmd_watcher_reindex,
        "files": cmd_files,
        "errors": cmd_errors,
        "users": cmd_users,
        "user-add": cmd_user_add,
        "user-rm": cmd_user_rm,
        "user-edit": cmd_user_edit,
        "feedback-stats": cmd_feedback_stats,
        "feedback-report": cmd_feedback_report,
        "tool-list": cmd_tool_list,
        "tool-approve": cmd_tool_approve,
        "tool-reject": cmd_tool_reject,
        "tool-show": cmd_tool_show,
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
