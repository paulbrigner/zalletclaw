#!/usr/bin/env python3
"""
Inspect local Zallet binary, config, and HTTP JSON-RPC status.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from zallet_rpc_util import (
    binary_supports_rpc,
    extract_rpc_auth,
    extract_rpc_binds,
    infer_http_url,
    json_rpc_request,
    load_toml_file,
    resolve_config_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether a local Zallet instance is reachable over JSON-RPC."
    )
    parser.add_argument("--binary", default="zallet", help="Path to the zallet binary.")
    parser.add_argument("--datadir", help="Wallet datadir used to infer zallet.toml.")
    parser.add_argument("--config", help="Explicit zallet.toml path.")
    parser.add_argument("--http-url", help="Explicit HTTP JSON-RPC URL.")
    parser.add_argument("--http-user", help="HTTP Basic auth username.")
    parser.add_argument(
        "--http-password-env",
        help="Environment variable that stores the HTTP Basic auth password.",
    )
    parser.add_argument(
        "--probe-method",
        default="getwalletinfo",
        help="RPC method used for the reachability probe.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP probe timeout in seconds.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def build_status(args: argparse.Namespace) -> dict[str, object]:
    config_path = resolve_config_path(args.datadir, args.config)
    config_data = load_toml_file(config_path)
    binds = extract_rpc_binds(config_data)
    auth_entries = extract_rpc_auth(config_data)
    http_url = infer_http_url(args.http_url, binds)

    password = None
    password_env_present = False
    if args.http_password_env:
        password = os.environ.get(args.http_password_env)
        password_env_present = password is not None

    probe = None
    if http_url:
        probe = json_rpc_request(
            http_url,
            args.probe_method,
            [],
            timeout=args.timeout,
            user=args.http_user,
            password=password,
        )

    notes: list[str] = []
    if auth_entries and any(entry.get("has_pwhash") for entry in auth_entries):
        notes.append(
            "Server auth includes at least one pwhash entry; this is sufficient for server-side verification."
        )
    if auth_entries and not any(entry.get("has_password") for entry in auth_entries):
        notes.append(
            "Config auth appears hash-only; direct HTTP with env-backed credentials is the safer default."
        )
    if args.http_password_env and not password_env_present:
        notes.append(
            f"Environment variable {args.http_password_env} is not set, so authenticated HTTP probes may fail."
        )
    if probe and probe["status_code"] == 401:
        notes.append("HTTP probe reached the server, but credentials were rejected or missing.")

    return {
        "binary": {
            "requested": args.binary,
            "resolved_path": shutil.which(args.binary) or args.binary,
            "exists": shutil.which(args.binary) is not None or Path(args.binary).exists(),
            "supports_rpc_cli": binary_supports_rpc(args.binary),
        },
        "config": {
            "path": str(config_path) if config_path else None,
            "exists": bool(config_path and config_path.exists()),
            "rpc_binds": binds,
            "rpc_auth": auth_entries,
        },
        "http": {
            "url": http_url,
            "client_user": args.http_user,
            "password_env": args.http_password_env,
            "password_env_present": password_env_present,
            "probe_method": args.probe_method,
            "probe": probe,
        },
        "notes": notes,
    }


def render_text(status: dict[str, object]) -> str:
    binary = status["binary"]
    config = status["config"]
    http = status["http"]
    probe = http["probe"]

    lines = [
        "Binary",
        f"- Requested: {binary['requested']}",
        f"- Resolved path: {binary['resolved_path']}",
        f"- Exists: {'yes' if binary['exists'] else 'no'}",
        f"- Supports `rpc` CLI subcommand: {'yes' if binary['supports_rpc_cli'] else 'no'}",
        "Config",
        f"- Path: {config['path'] or 'not inferred'}",
        f"- Exists: {'yes' if config['exists'] else 'no'}",
        f"- rpc.bind entries: {', '.join(config['rpc_binds']) if config['rpc_binds'] else 'none'}",
    ]

    auth_entries = config["rpc_auth"]
    if auth_entries:
        auth_desc = []
        for entry in auth_entries:
            modes = []
            if entry.get("has_password"):
                modes.append("password")
            if entry.get("has_pwhash"):
                modes.append("pwhash")
            auth_desc.append(f"{entry.get('user') or '<missing user>'} ({'/'.join(modes) or 'none'})")
        lines.append(f"- rpc.auth entries: {', '.join(auth_desc)}")
    else:
        lines.append("- rpc.auth entries: none")

    lines.extend(
        [
            "HTTP JSON-RPC",
            f"- URL: {http['url'] or 'not resolved'}",
            f"- Client user: {http['client_user'] or 'none'}",
            f"- Password env: {http['password_env'] or 'none'}",
            f"- Password env present: {'yes' if http['password_env_present'] else 'no'}",
        ]
    )

    if probe is None:
        lines.append("- Probe: skipped because no HTTP URL was available")
    else:
        status_code = probe["status_code"] if probe["status_code"] is not None else "transport error"
        lines.append(f"- Probe status: {status_code}")
        lines.append(f"- Probe HTTP success: {'yes' if probe['http_ok'] else 'no'}")
        if probe["rpc_error"] is not None:
            lines.append(f"- Probe RPC error: {json.dumps(probe['rpc_error'], sort_keys=True)}")
        if probe["transport_error"]:
            lines.append(f"- Probe transport error: {probe['transport_error']}")

    notes = status["notes"]
    if notes:
        lines.append("Notes")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    status = build_status(args)

    if args.format == "json":
        json.dump(status, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(render_text(status))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
