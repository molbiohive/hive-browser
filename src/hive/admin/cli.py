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


def _post_json(args, path: str, body: dict):
    client, headers = _client(args)
    try:
        r = client.post(path, headers=headers, json=body)
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


# ── ps ────────────────────────────────────────────────────────────────


def cmd_ps_list(args):
    data = _get(args, "/admin/ps")
    procs = data.get("processes", [])
    if not procs:
        print("No registered processes.")
        return
    for p in procs:
        state = p["state"]
        started = p.get("started_at", "")
        if started:
            started = started[:19].replace("T", " ")
        info = p.get("result") or p.get("error") or ""
        print(f"  {state:<10s} {p['name']:<12s} {p['description']:<25s} {started}  {info}")


def cmd_ps_start(args):
    _pp(_post(args, f"/admin/ps/{args.name}/start"))


def cmd_ps_stop(args):
    _pp(_post(args, f"/admin/ps/{args.name}/stop"))


def cmd_ps_pause(args):
    _pp(_post(args, f"/admin/ps/{args.name}/pause"))


def cmd_ps_resume(args):
    _pp(_post(args, f"/admin/ps/{args.name}/resume"))


# ── db ────────────────────────────────────────────────────────────────


def cmd_db_errors(args):
    data = _get(args, "/admin/db/errors")
    errors = data.get("errors", [])
    if not errors:
        print("No parse errors.")
        return
    for e in errors:
        print(f"  {e['path']}")
        print(f"    {e['error']}")


def cmd_db_audit(args):
    data = _post_json(args, "/admin/db/audit", {"verbose": args.verbose})
    t = data["totals"]
    fi = t["indexed_files"]
    print("Database audit:")
    print(f"  Files:      {fi['active']} active, {fi['error']} errors, {fi['deleted']} deleted")
    print(f"  Sequences:  {t['sequences']}")
    print(f"  Parts:      {t['parts']}")
    print(f"  Instances:  {t['part_instances']}")
    print(f"  Libraries:  {t['libraries']}")
    hd = data["hash_duplicates"]
    print(f"  Hash dupes: {hd['groups']} groups ({hd['files']} files)")
    nd = data["inode_duplicates"]
    print(f"  Inode dupes: {nd['groups']} groups ({nd['files']} files)")
    print(f"  Orphans:    {data['orphans']}")
    if args.verbose:
        for group in data.get("hash_duplicate_details", []):
            print(f"\n  Hash {group['hash']}... ({group['count']} copies):")
            for f in group["files"]:
                print(f"    [{f['id']}] {f['path']}")
        for group in data.get("inode_duplicate_details", []):
            print(f"\n  Inode group ({group['count']} copies):")
            for f in group["files"]:
                print(f"    [{f['id']}] {f['path']}")
        for o in data.get("orphan_details", []):
            print(f"\n  Orphan [{o['id']}] {o['path']}")


def cmd_db_dedupe(args):
    data = _post_json(args, "/admin/db/dedupe", {"dry_run": args.dry_run})
    prefix = "Would remove" if data["dry_run"] else "Removed"
    print(f"{prefix} {data['removed']} duplicate file(s)")
    for d in data.get("details", []):
        print(f"  [{d['id']}] {d['path']}  (hash: {d['hash']}...)")


def cmd_db_prune(args):
    data = _post_json(
        args,
        "/admin/db/prune",
        {
            "dry_run": args.dry_run,
            "no_archive": args.no_archive,
        },
    )
    prefix = "Would prune" if data.get("dry_run") else "Pruned"
    print(f"{prefix} {data['pruned']} orphan file(s)")
    for d in data.get("details", []):
        print(f"  [{d['id']}] {d['path']}")


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
            lines.append(f"| {i} | {date} | {username} | {fb.rating} | {fb.priority} | {comment} |")
        out = args.output
        with open(out, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Report written to {out} ({len(items)} entries)")

    asyncio.run(_run_db(_report))


# ── library ───────────────────────────────────────────────────────────


def cmd_library_list(args):
    data = _get(args, "/admin/libraries")
    libs = data.get("libraries", [])
    if not libs:
        print("No libraries.")
        return
    for lib in libs:
        src = lib["source"]
        desc = lib.get("description") or ""
        print(
            f"  {lib['id']:3d}  {lib['name']:<20s}  {src:<8s}  {lib['member_count']:4d} parts  {desc}"
        )


def cmd_library_create(args):
    data = _post_json(
        args,
        "/admin/libraries",
        {
            "name": args.name,
            "description": args.description,
        },
    )
    print(f"Created library: {data['name']} (id: {data['id']})")


def cmd_library_add(args):
    # Resolve library id by name
    libs = _get(args, "/admin/libraries").get("libraries", [])
    lib = next((l for l in libs if l["name"] == args.library_name), None)
    if not lib:
        print(f"Library not found: {args.library_name}", file=sys.stderr)
        sys.exit(1)
    data = _post_json(args, f"/admin/libraries/{lib['id']}/add", {"pid": args.pid})
    print(f"{data.get('status', 'done')}: PID {args.pid} -> {args.library_name}")


def cmd_library_show(args):
    libs = _get(args, "/admin/libraries").get("libraries", [])
    lib = next((l for l in libs if l["name"] == args.library_name), None)
    if not lib:
        print(f"Library not found: {args.library_name}", file=sys.stderr)
        sys.exit(1)
    print(f"Library: {lib['name']}")
    print(f"  Source: {lib['source']}")
    print(f"  Parts:  {lib['member_count']}")
    if lib.get("description"):
        print(f"  Desc:   {lib['description']}")


# ── tools ─────────────────────────────────────────────────────────────


def cmd_tools_list(args):
    async def _list(s):
        from sqlalchemy import select as sel
        from hive.db.models import ToolApproval

        rows = (
            (await s.execute(sel(ToolApproval).order_by(ToolApproval.created_at))).scalars().all()
        )
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

        record = (
            await s.execute(sel(ToolApproval).where(ToolApproval.filename == args.filename))
        ).scalar_one_or_none()
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

        record = (
            await s.execute(sel(ToolApproval).where(ToolApproval.filename == args.filename))
        ).scalar_one_or_none()
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

    # admin ps <list|start|stop|pause|resume>
    _add_group(
        sub,
        "ps",
        "Background process management",
        [
            ("list", "List all processes", cmd_ps_list, []),
            (
                "start",
                "Start a process",
                cmd_ps_start,
                [
                    (["name"], {"help": "Process name (scan, watcher, rescan, reindex)"}),
                ],
            ),
            (
                "stop",
                "Stop a process",
                cmd_ps_stop,
                [
                    (["name"], {"help": "Process name"}),
                ],
            ),
            (
                "pause",
                "Pause a process",
                cmd_ps_pause,
                [
                    (["name"], {"help": "Process name"}),
                ],
            ),
            (
                "resume",
                "Resume a paused process",
                cmd_ps_resume,
                [
                    (["name"], {"help": "Process name"}),
                ],
            ),
        ],
    )

    # admin db <errors|audit|dedupe|prune>
    _add_group(
        sub,
        "db",
        "Database inspection and cleanup",
        [
            ("errors", "List parse errors", cmd_db_errors, []),
            (
                "audit",
                "Audit database integrity",
                cmd_db_audit,
                [
                    (
                        ["-v", "--verbose"],
                        {"action": "store_true", "help": "Show individual items"},
                    ),
                ],
            ),
            (
                "dedupe",
                "Remove duplicate file records",
                cmd_db_dedupe,
                [
                    (["--dry-run"], {"action": "store_true", "help": "Preview only, don't delete"}),
                ],
            ),
            (
                "prune",
                "Remove records for missing files",
                cmd_db_prune,
                [
                    (["--dry-run"], {"action": "store_true", "help": "Preview only, don't delete"}),
                    (["--no-archive"], {"action": "store_true", "help": "Skip JSONL archiving"}),
                ],
            ),
        ],
    )

    # admin users <list|add|rm|edit>
    _add_group(
        sub,
        "user",
        "User management",
        [
            ("list", "List all users", cmd_users_list, []),
            (
                "add",
                "Create a new user",
                cmd_users_add,
                [
                    (["username"], {"help": "Display name"}),
                ],
            ),
            (
                "rm",
                "Remove a user by slug",
                cmd_users_rm,
                [
                    (["slug"], {"help": "User slug to remove"}),
                ],
            ),
            (
                "edit",
                "Rename a user",
                cmd_users_edit,
                [
                    (["slug"], {"help": "Current user slug"}),
                    (["new_name"], {"help": "New display name"}),
                ],
            ),
        ],
    )

    # admin feedback <stats|report>
    _add_group(
        sub,
        "feedback",
        "User feedback",
        [
            ("stats", "Show feedback summary", cmd_feedback_stats, []),
            (
                "report",
                "Generate feedback report (.md)",
                cmd_feedback_report,
                [
                    (["-o", "--output"], {"default": "feedback_report.md", "help": "Output file"}),
                ],
            ),
        ],
    )

    # admin library <list|create|add|show>
    _add_group(
        sub,
        "library",
        "Part library management",
        [
            ("list", "List all libraries", cmd_library_list, []),
            (
                "create",
                "Create a manual library",
                cmd_library_create,
                [
                    (["name"], {"help": "Library name"}),
                    (["--description"], {"default": None, "help": "Library description"}),
                ],
            ),
            (
                "add",
                "Add a part to a library",
                cmd_library_add,
                [
                    (["library_name"], {"help": "Library name"}),
                    (["pid"], {"type": int, "help": "Part ID (PID)"}),
                ],
            ),
            (
                "show",
                "Show library details",
                cmd_library_show,
                [
                    (["library_name"], {"help": "Library name"}),
                ],
            ),
        ],
    )

    # admin tools <list|approve|reject|show>
    _add_group(
        sub,
        "tool",
        "External tool quarantine",
        [
            ("list", "List tools and approval status", cmd_tools_list, []),
            (
                "approve",
                "Approve a quarantined tool",
                cmd_tools_approve,
                [
                    (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
                ],
            ),
            (
                "reject",
                "Reject a quarantined tool",
                cmd_tools_reject,
                [
                    (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
                ],
            ),
            (
                "show",
                "Show tool source code for review",
                cmd_tools_show,
                [
                    (["filename"], {"help": "Tool filename (e.g. my_tool.py)"}),
                ],
            ),
        ],
    )

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
