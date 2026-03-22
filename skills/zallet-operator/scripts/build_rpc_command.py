#!/usr/bin/env python3
"""
Build a shell-safe Zallet JSON-RPC command using either the CLI RPC client or direct HTTP.
"""

from __future__ import annotations

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a shell-safe Zallet JSON-RPC command from JSON parameters."
    )
    parser.add_argument("--method", required=True, help="RPC method name.")
    parser.add_argument(
        "--transport",
        choices=("auto", "cli", "http"),
        default="auto",
        help="Transport to emit. 'auto' uses the CLI RPC client when available and falls back to HTTP.",
    )
    parser.add_argument(
        "--binary",
        default="zallet",
        help="Path to the zallet binary for CLI transport detection and command generation.",
    )
    parser.add_argument(
        "--params-json",
        help="JSON array of positional parameters to pass to the RPC method.",
    )
    parser.add_argument(
        "--params-file",
        help="Path to a file containing a JSON array of positional parameters.",
    )
    parser.add_argument(
        "--datadir",
        help="Absolute datadir path to pass to zallet for CLI transport.",
    )
    parser.add_argument(
        "--config",
        help="Config path to pass to zallet for CLI transport.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="RPC timeout in seconds. Maps to --timeout for CLI or --max-time for curl.",
    )
    parser.add_argument(
        "--http-url",
        help="HTTP JSON-RPC endpoint, for example http://127.0.0.1:28232.",
    )
    parser.add_argument(
        "--http-user",
        help="HTTP Basic auth username. Pair with --http-password-env.",
    )
    parser.add_argument(
        "--http-password-env",
        help="Environment variable name holding the HTTP Basic auth password.",
    )
    parser.add_argument(
        "--format",
        choices=("shell", "argv-json"),
        default="shell",
        help="Output format.",
    )
    return parser.parse_args()


def load_params(args: argparse.Namespace) -> list[object]:
    if args.params_json and args.params_file:
        raise ValueError("pass either --params-json or --params-file, not both")

    if args.params_file:
        raw = Path(args.params_file).read_text(encoding="utf-8")
    else:
        raw = args.params_json or "[]"

    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON parameter array: {exc}") from exc

    if not isinstance(params, list):
        raise ValueError("parameter input must decode to a JSON array")

    return params


def binary_supports_rpc(binary: str) -> bool:
    try:
        result = subprocess.run(
            [binary, "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False

    help_text = (result.stdout or "") + "\n" + (result.stderr or "")
    return re.search(r"^\s+rpc\s+", help_text, re.MULTILINE) is not None


def choose_transport(args: argparse.Namespace) -> str:
    if args.transport in ("cli", "http"):
        return args.transport

    if binary_supports_rpc(args.binary):
        return "cli"

    return "http"


def build_cli_command(args: argparse.Namespace, params: list[object]) -> list[str]:
    command = [args.binary]

    if args.datadir:
        command.extend(["--datadir", args.datadir])

    if args.config:
        command.extend(["--config", args.config])

    command.append("rpc")

    if args.timeout is not None:
        command.extend(["--timeout", str(args.timeout)])

    command.append(args.method)

    for param in params:
        command.append(json.dumps(param, ensure_ascii=True, separators=(",", ":")))

    return command


def build_http_command(args: argparse.Namespace, params: list[object]) -> list[str]:
    if not args.http_url:
        raise ValueError("http transport requires --http-url")

    if bool(args.http_user) != bool(args.http_password_env):
        raise ValueError(
            "http auth requires both --http-user and --http-password-env, or neither"
        )

    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": args.method, "params": params},
        ensure_ascii=True,
        separators=(",", ":"),
    )

    command = ["curl", "-sS"]

    if args.timeout is not None:
        command.extend(["--max-time", str(args.timeout)])

    command.extend(
        [
            "-H",
            "content-type: application/json",
            "--data",
            payload,
            args.http_url,
        ]
    )

    return command


def shell_quote_with_env(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
    )
    return f'"{escaped}"'


def render_shell(
    transport: str,
    command: list[str],
    http_user: str | None,
    http_password_env: str | None,
) -> str:
    if transport != "http" or not http_user:
        return shlex.join(command)

    rendered: list[str] = []
    inserted_auth = False

    for token in command:
        rendered.append(shlex.quote(token))
        if token == "curl" and not inserted_auth:
            auth_token = f"{http_user}:${{{http_password_env}}}"
            rendered.extend(["-u", shell_quote_with_env(auth_token)])
            inserted_auth = True

    return " ".join(rendered)


def main() -> int:
    args = parse_args()

    try:
        params = load_params(args)
        transport = choose_transport(args)
        if transport == "cli":
            command = build_cli_command(args, params)
        else:
            command = build_http_command(args, params)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "argv-json":
        json.dump(command, sys.stdout)
        sys.stdout.write("\n")
    else:
        print(
            render_shell(
                transport,
                command,
                args.http_user,
                args.http_password_env,
            )
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
