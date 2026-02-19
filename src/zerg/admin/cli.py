"""Admin CLI — talk to a running Zerg server."""

import argparse
import json
import sys

import httpx

from zerg.admin.token import ZERG_HOME, load_token

DEFAULT_URL = "http://localhost:8080"


def _client(args) -> tuple[httpx.Client, dict]:
    """Build HTTP client and auth headers."""
    token = args.token or load_token()
    if not token:
        print(f"No admin token found. Check {ZERG_HOME / 'admin.token'}", file=sys.stderr)
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
        print(f"No token found at {ZERG_HOME / 'admin.token'}", file=sys.stderr)
        sys.exit(1)


# ── Entry point ──────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        prog="zerg-admin",
        description="Admin CLI for Zerg Browser server",
    )
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help=f"Server URL (default: {DEFAULT_URL})",
    )
    parser.add_argument(
        "--token", default=None,
        help="Admin token (default: read from ~/.zerg/admin.token)",
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
    }

    dispatch[args.command](args)


if __name__ == "__main__":
    main()
