"""Admin CLI for Hive Browser."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

from hive.admin.token import HIVE_HOME, load_token

DEFAULT_URL = "http://localhost:8080"


# ── HTTP helpers ──────────────────────────────────────────────────────


def _client(args) -> tuple[httpx.Client, dict]:
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
    print(json.dumps(data, indent=2))


# ── DB helper (direct commands, no server needed) ────────────────────


def _db_url():
    from hive.config import load_config
    return load_config().database.url


async def _run_db(coro_fn):
    from hive.db import session as db
    await db.init_db(type("C", (), {"url": _db_url()})())
    async with db.async_session_factory() as s:
        await coro_fn(s)


# ── Top-level commands ────────────────────────────────────────────────


def cmd_status(args):
    _pp(_get(args, "/admin/status"))


def cmd_health(args):
    _pp(_get(args, "/admin/health"))


def cmd_token(args):
    token = load_token()
    if token:
        print(token)
    else:
        print(f"No token found at {HIVE_HOME / 'admin.token'}", file=sys.stderr)
        sys.exit(1)


# ── watcher ───────────────────────────────────────────────────────────


def cmd_watcher_start(args):
    _pp(_post(args, "/admin/watcher/start"))


def cmd_watcher_stop(args):
    _pp(_post(args, "/admin/watcher/stop"))


def cmd_watcher_rescan(args):
    _pp(_post(args, "/admin/watcher/rescan"))


def cmd_watcher_reindex(args):
    _pp(_post(args, "/admin/watcher/reindex"))


# ── db ────────────────────────────────────────────────────────────────


def cmd_db_files(args):
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


def cmd_db_errors(args):
    data = _get(args, "/admin/db/errors")
    errors = data.get("errors", [])
    if not errors:
        print("No parse errors.")
        return
    for e in errors:
        print(f"  {e['path']}")
        print(f"    {e['error']}")


# ── users ─────────────────────────────────────────────────────────────


def cmd_users_list(args):
    async def _list(s):
        from hive.users.service import list_users
        users = await list_users(s)
        if not users:
            print("No users.")
            return
        for u in users:
            print(f"  {u.id:3d}  {u.slug:<20s}  {u.username}")
    asyncio.run(_run_db(_list))


def cmd_users_add(args):
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
    asyncio.run(_run_db(_add))


def cmd_users_rm(args):
    async def _rm(s):
        from sqlalchemy import delete
        from hive.db.models import User
        result = await s.execute(delete(User).where(User.slug == args.slug))
        await s.commit()
        if result.rowcount:
            print(f"Deleted user: {args.slug}")
        else:
            print(f"User not found: {args.slug}", file=sys.stderr)
            sys.exit(1)
    asyncio.run(_run_db(_rm))


def cmd_users_edit(args):
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
    asyncio.run(_run_db(_edit))


# ── feedback ──────────────────────────────────────────────────────────


def cmd_feedback_stats(args):
    async def _stats(s):
        from hive.users.service import feedback_stats
        st = await feedback_stats(s)
        total = st["total"]
        if not total:
            print("No feedback yet.")
            return
        good, bad = st["good"], st["bad"]
        good_pct = good * 100 // total if total else 0
        bad_pct = bad * 100 // total if total else 0
        print("Feedback stats:")
        print(f"  Total: {total}")
        print(f"  Good:  {good} ({good_pct}%)")
        print(f"  Bad:   {bad} ({bad_pct}%)")
        if st["last_at"]:
            print(f"  Last:  {st['last_at']} by {st['last_by']}")
    asyncio.run(_run_db(_stats))


def cmd_feedback_report(args):
    async def _report(s):
        from hive.users.service import feedback_stats, list_feedback
        items = await list_feedback(s)
        if not items:
            print("No feedback to report.")
            return
        st = await feedback_stats(s)
        from datetime import UTC, datetime
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
        out = args.output
        with open(out, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Report written to {out} ({len(items)} entries)")
    asyncio.run(_run_db(_report))


# ── tools ─────────────────────────────────────────────────────────────


def cmd_tools_list(args):
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
    asyncio.run(_run_db(_list))


def cmd_tools_approve(args):
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
    asyncio.run(_run_db(_approve))


def cmd_tools_reject(args):
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
    asyncio.run(_run_db(_reject))


def cmd_tools_show(args):
    from hive.config import load_config
    tools_dir = Path(load_config().tools_dir)
    tool_file = tools_dir / args.filename
    if not tool_file.is_file():
        print(f"File not found: {tool_file}", file=sys.stderr)
        sys.exit(1)
    print(tool_file.read_text())


# ── Parser ────────────────────────────────────────────────────────────


def _add_group(sub, name, help_text, commands):
    """Add a subcommand group with nested sub-subcommands."""
    group = sub.add_parser(name, help=help_text)
    gsub = group.add_subparsers(dest=f"{name}_cmd", required=True)
    for cmd_name, cmd_help, cmd_fn, cmd_args in commands:
        p = gsub.add_parser(cmd_name, help=cmd_help)
        for arg_args, arg_kwargs in cmd_args:
            p.add_argument(*arg_args, **arg_kwargs)
        p.set_defaults(func=cmd_fn)


def main():
    parser = argparse.ArgumentParser(
        prog="admin",
        description="Admin CLI for Hive Browser",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help=f"Server URL (default: {DEFAULT_URL})")
    parser.add_argument("--token", default=None, help="Admin token (default: ~/.hive/admin.token)")

    sub = parser.add_subparsers(dest="command", required=True)

    # Top-level commands
    for name, help_text, fn in [
        ("status", "System status (DB counts, watcher state)", cmd_status),
        ("health", "Server health check", cmd_health),
        ("token", "Show current admin token", cmd_token),
    ]:
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=fn)

    # admin watcher <start|stop|rescan|reindex>
    _add_group(sub, "watcher", "File watcher management", [
        ("start", "Start the file watcher", cmd_watcher_start, []),
        ("stop", "Stop the file watcher", cmd_watcher_stop, []),
        ("rescan", "Force full directory rescan", cmd_watcher_rescan, []),
        ("reindex", "Re-parse all files (reset hashes)", cmd_watcher_reindex, []),
    ])

    # admin db <files|errors>
    _add_group(sub, "db", "Database inspection", [
        ("files", "List indexed files", cmd_db_files, []),
        ("errors", "List parse errors", cmd_db_errors, []),
    ])

    # admin users <list|add|rm|edit>
    _add_group(sub, "user", "User management", [
        ("list", "List all users", cmd_users_list, []),
        ("add", "Create a new user", cmd_users_add, [
            (["username"], {"help": "Display name"}),
        ]),
        ("rm", "Remove a user by slug", cmd_users_rm, [
            (["slug"], {"help": "User slug to remove"}),
        ]),
        ("edit", "Rename a user", cmd_users_edit, [
            (["slug"], {"help": "Current user slug"}),
            (["new_name"], {"help": "New display name"}),
        ]),
    ])

    # admin feedback <stats|report>
    _add_group(sub, "feedback", "User feedback", [
        ("stats", "Show feedback summary", cmd_feedback_stats, []),
        ("report", "Generate feedback report (.md)", cmd_feedback_report, [
            (["-o", "--output"], {"default": "feedback_report.md", "help": "Output file"}),
        ]),
    ])

    # admin tools <list|approve|reject|show>
    _add_group(sub, "tool", "External tool quarantine", [
        ("list", "List tools and approval status", cmd_tools_list, []),
        ("approve", "Approve a quarantined tool", cmd_tools_approve, [
            (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
        ]),
        ("reject", "Reject a quarantined tool", cmd_tools_reject, [
            (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
        ]),
        ("show", "Show tool source code for review", cmd_tools_show, [
            (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
        ]),
    ])

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
