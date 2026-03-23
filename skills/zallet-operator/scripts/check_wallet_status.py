#!/usr/bin/env python3
"""
Inspect local Zallet binary, config, and HTTP JSON-RPC status.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    resolve_http_password,
    resolve_config_path,
)

ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*m")
CHAIN_TIP_RE = re.compile(r"New chain tip:\s+(?P<height>\d+)\s+(?P<hash>[0-9a-fA-F]+)")


def parse_ps_command(line: str) -> str | None:
    parts = line.strip().split(None, 10)
    if len(parts) < 11:
        return None

    return parts[10]


def extract_datadir_from_argv(argv: list[str]) -> str | None:
    for index, token in enumerate(argv):
        if token in ("-d", "--datadir") and index + 1 < len(argv):
            return argv[index + 1]
        if token.startswith("--datadir="):
            return token.split("=", 1)[1]

    return None


def discover_live_wallet_process() -> dict[str, object] | None:
    try:
        result = subprocess.run(
            ["ps", "aux"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None

    for line in (result.stdout or "").splitlines():
        command = parse_ps_command(line)
        if not command or "zallet" not in command or " start" not in command:
            continue

        try:
            argv = shlex.split(command)
        except ValueError:
            continue

        if not argv:
            continue

        binary = argv[0]
        if Path(binary).name != "zallet":
            continue

        datadir = extract_datadir_from_argv(argv)
        binary_path = Path(binary).expanduser()
        resolved_binary = binary_path.resolve(strict=False) if binary_path.is_absolute() else binary_path

        resolved_datadir = None
        if datadir:
            datadir_path = Path(datadir).expanduser()
            if datadir_path.is_absolute():
                resolved_datadir = datadir_path.resolve(strict=False)
            elif binary_path.is_absolute():
                resolved_datadir = (resolved_binary.parent / datadir_path).resolve(strict=False)

        return {
            "command": command,
            "argv": argv,
            "binary": str(resolved_binary) if binary_path.is_absolute() else binary,
            "datadir": str(resolved_datadir) if resolved_datadir else datadir,
        }

    return None


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
        "--http-password-keychain-service",
        help="macOS Keychain service name used to look up the HTTP Basic auth password.",
    )
    parser.add_argument(
        "--http-password-keychain-account",
        help="macOS Keychain account name. Defaults to --http-user when omitted.",
    )
    parser.add_argument(
        "--probe-method",
        default="getwalletinfo",
        help="RPC method used for the reachability probe.",
    )
    parser.add_argument(
        "--recent-transaction-limit",
        type=int,
        default=3,
        help="Number of recent transactions to summarize per account.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=5,
        help="HTTP probe timeout in seconds.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json", "summary"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--timezone",
        default="utc",
        help=(
            "Timezone for human-oriented timestamps. Use 'utc', 'local', or an IANA timezone "
            "such as 'America/New_York'."
        ),
    )
    return parser.parse_args()


def infer_http_user(auth_entries: list[dict[str, object]]) -> str | None:
    users: list[str] = []
    for entry in auth_entries:
        user = entry.get("user")
        if isinstance(user, str) and user and user not in users:
            users.append(user)

    return users[0] if len(users) == 1 else None


def rpc_call_ok(response: dict[str, object] | None) -> bool:
    return bool(
        response
        and response.get("http_ok")
        and response.get("status_code") == 200
        and response.get("rpc_error") is None
    )


def rpc_error_detail(response: dict[str, object] | None) -> str:
    if response is None:
        return "no response"

    rpc_error = response.get("rpc_error")
    if rpc_error is not None:
        return json.dumps(rpc_error, sort_keys=True)

    transport_error = response.get("transport_error")
    if transport_error:
        return str(transport_error)

    status_code = response.get("status_code")
    if status_code is not None and status_code != 200:
        return f"HTTP {status_code}"

    return "unknown error"


def format_zat(value: object) -> str | None:
    if not isinstance(value, int):
        return None

    return f"{value / 100000000:.8f}"


def transaction_sort_key(tx: dict[str, object]) -> tuple[int, str]:
    block_time = tx.get("block_time")
    if not isinstance(block_time, int):
        block_time = 0

    txid = tx.get("txid")
    return (block_time, txid if isinstance(txid, str) else "")


def summarize_transaction(tx: dict[str, object]) -> dict[str, object]:
    delta = tx.get("account_balance_delta")
    delta_zec = format_zat(delta)
    absolute_delta_zec = format_zat(abs(delta)) if isinstance(delta, int) else None

    if isinstance(delta, int):
        if delta < 0:
            direction = "sent"
        elif delta > 0:
            direction = "received"
        else:
            direction = "neutral"
    else:
        direction = "unknown"

    return {
        "block_datetime": tx.get("block_datetime"),
        "txid": tx.get("txid"),
        "account_balance_delta_zat": delta,
        "account_balance_delta_zec": delta_zec,
        "absolute_balance_delta_zec": absolute_delta_zec,
        "direction": direction,
        "expired_unmined": tx.get("expired_unmined"),
        "mined_height": tx.get("mined_height"),
        "received_note_count": tx.get("received_note_count"),
        "sent_note_count": tx.get("sent_note_count"),
    }


def looks_like_placeholder_getwalletinfo(result: object) -> bool:
    if not isinstance(result, dict):
        return False

    return bool(
        result.get("walletversion") == 0
        and result.get("mnemonic_seedfp") == "TODO"
        and result.get("txcount") == 0
    )


def resolve_output_timezone(name: str):
    normalized = name.strip()
    if normalized.lower() == "utc":
        return timezone.utc

    if normalized.lower() == "local":
        local_timezone = datetime.now().astimezone().tzinfo
        return local_timezone or timezone.utc

    try:
        return ZoneInfo(normalized)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {name}") from exc


def parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed


def render_timestamp(value: object, output_timezone) -> str | None:
    parsed = parse_timestamp(value)
    if parsed is None:
        return value if isinstance(value, str) else None

    return parsed.astimezone(output_timezone).strftime("%Y-%m-%d %I:%M:%S %p %Z")


def infer_log_path(datadir: str | None, config_path: Path | None) -> Path | None:
    if datadir:
        return Path(datadir).expanduser().resolve() / "zallet.log"

    if config_path is not None:
        return config_path.parent / "zallet.log"

    return None


def resolve_datadir_path(datadir: str | None, config_path: Path | None) -> Path | None:
    if datadir:
        return Path(datadir).expanduser().resolve()

    if config_path is not None:
        return config_path.parent

    return None


def read_log_status(log_path: Path | None) -> dict[str, object]:
    status: dict[str, object] = {
        "path": str(log_path) if log_path else None,
        "exists": bool(log_path and log_path.exists()),
        "latest_chain_tip": None,
        "recently_reached_chain_tip": None,
        "latest_reached_chain_tip_log_time": None,
    }

    if log_path is None or not log_path.exists():
        return status

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()[-400:]
    status["recently_reached_chain_tip"] = False

    for raw_line in lines:
        line = ANSI_ESCAPE_RE.sub("", raw_line)
        parts = line.split(maxsplit=1)
        log_time = parts[0] if parts else None

        if "Reached chain tip, streaming mempool" in line:
            status["recently_reached_chain_tip"] = True
            status["latest_reached_chain_tip_log_time"] = log_time

        match = CHAIN_TIP_RE.search(line)
        if match:
            status["latest_chain_tip"] = {
                "height": int(match.group("height")),
                "hash": match.group("hash"),
                "log_time": log_time,
            }

    return status


def ensure_account_summary(
    accounts: list[dict[str, object]],
    account_index: dict[str, dict[str, object]],
    account_uuid: str,
) -> dict[str, object]:
    account = account_index.get(account_uuid)
    if account is not None:
        return account

    account = {
        "account_uuid": account_uuid,
        "name": None,
        "seedfp": None,
        "zip32_account_index": None,
        "known_address_count": None,
        "spendable_balance_zat": None,
        "spendable_balance_zec": None,
        "recent_transactions": [],
    }
    account_index[account_uuid] = account
    accounts.append(account)
    return account


def build_wallet_summary(
    http_url: str,
    http_user: str | None,
    password: str | None,
    timeout: int,
    recent_transaction_limit: int,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "summary_attempted": True,
        "summary_available": False,
        "account_count": None,
        "accounts": [],
        "note_counts": None,
        "operation_ids": None,
        "method_errors": {},
    }

    accounts: list[dict[str, object]] = []
    account_index: dict[str, dict[str, object]] = {}

    accounts_response = json_rpc_request(
        http_url,
        "z_listaccounts",
        [True],
        timeout=timeout,
        user=http_user,
        password=password,
    )
    if rpc_call_ok(accounts_response) and isinstance(accounts_response.get("rpc_result"), list):
        for item in accounts_response["rpc_result"]:
            if not isinstance(item, dict):
                continue
            account_uuid = item.get("account_uuid")
            if not isinstance(account_uuid, str):
                continue

            account = ensure_account_summary(accounts, account_index, account_uuid)
            account["name"] = item.get("name")
            account["seedfp"] = item.get("seedfp")
            account["zip32_account_index"] = item.get("zip32_account_index")
            addresses = item.get("addresses")
            if isinstance(addresses, list):
                account["known_address_count"] = len(addresses)
    else:
        summary["method_errors"]["z_listaccounts"] = rpc_error_detail(accounts_response)

    balances_response = json_rpc_request(
        http_url,
        "z_getbalances",
        [],
        timeout=timeout,
        user=http_user,
        password=password,
    )
    if rpc_call_ok(balances_response) and isinstance(balances_response.get("rpc_result"), dict):
        balance_accounts = balances_response["rpc_result"].get("accounts")
        if isinstance(balance_accounts, list):
            for item in balance_accounts:
                if not isinstance(item, dict):
                    continue
                account_uuid = item.get("account_uuid")
                if not isinstance(account_uuid, str):
                    continue

                account = ensure_account_summary(accounts, account_index, account_uuid)
                spendable = (
                    item.get("total", {}).get("spendable", {}).get("valueZat")
                    if isinstance(item.get("total"), dict)
                    else None
                )
                account["spendable_balance_zat"] = spendable
                account["spendable_balance_zec"] = format_zat(spendable)
    else:
        summary["method_errors"]["z_getbalances"] = rpc_error_detail(balances_response)

    note_counts_response = json_rpc_request(
        http_url,
        "z_getnotescount",
        [],
        timeout=timeout,
        user=http_user,
        password=password,
    )
    if rpc_call_ok(note_counts_response) and isinstance(note_counts_response.get("rpc_result"), dict):
        summary["note_counts"] = note_counts_response["rpc_result"]
    else:
        summary["method_errors"]["z_getnotescount"] = rpc_error_detail(note_counts_response)

    operation_ids_response = json_rpc_request(
        http_url,
        "z_listoperationids",
        [],
        timeout=timeout,
        user=http_user,
        password=password,
    )
    if rpc_call_ok(operation_ids_response) and isinstance(operation_ids_response.get("rpc_result"), list):
        summary["operation_ids"] = operation_ids_response["rpc_result"]
    else:
        summary["method_errors"]["z_listoperationids"] = rpc_error_detail(operation_ids_response)

    tx_limit = max(1, recent_transaction_limit)
    transaction_fetch_limit = max(100, tx_limit)
    for account in accounts:
        account_uuid = account.get("account_uuid")
        if not isinstance(account_uuid, str):
            continue

        transactions_response = json_rpc_request(
            http_url,
            "z_listtransactions",
            [account_uuid, None, None, 0, transaction_fetch_limit],
            timeout=timeout,
            user=http_user,
            password=password,
        )
        if rpc_call_ok(transactions_response) and isinstance(
            transactions_response.get("rpc_result"), list
        ):
            ordered = sorted(transactions_response["rpc_result"], key=transaction_sort_key)
            account["recent_transactions"] = [
                summarize_transaction(tx)
                for tx in ordered[-tx_limit:]
                if isinstance(tx, dict)
            ]
        else:
            summary["method_errors"][f"z_listtransactions:{account_uuid}"] = rpc_error_detail(
                transactions_response
            )

    summary["accounts"] = accounts
    summary["account_count"] = len(accounts)
    summary["summary_available"] = bool(
        accounts or summary["note_counts"] is not None or summary["operation_ids"] is not None
    )

    return summary


def build_status(args: argparse.Namespace) -> dict[str, object]:
    live_process = discover_live_wallet_process()

    effective_binary = args.binary
    if args.binary == "zallet" and live_process and isinstance(live_process.get("binary"), str):
        effective_binary = str(live_process["binary"])

    effective_datadir = args.datadir
    if effective_datadir is None and live_process and isinstance(live_process.get("datadir"), str):
        effective_datadir = str(live_process["datadir"])

    config_path = resolve_config_path(effective_datadir, args.config)
    datadir_path = resolve_datadir_path(effective_datadir, config_path)
    config_data = load_toml_file(config_path)
    binds = extract_rpc_binds(config_data)
    auth_entries = extract_rpc_auth(config_data)
    http_url = infer_http_url(args.http_url, binds)
    inferred_http_user = infer_http_user(auth_entries)
    effective_http_user = args.http_user or inferred_http_user

    password_info = resolve_http_password(
        password_env=args.http_password_env,
        keychain_service=args.http_password_keychain_service,
        keychain_account=args.http_password_keychain_account,
        default_keychain_account=effective_http_user,
    )

    probe = None
    if http_url:
        probe = json_rpc_request(
            http_url,
            args.probe_method,
            [],
            timeout=args.timeout,
            user=effective_http_user,
            password=password_info["password"],
        )

    log_status = read_log_status(infer_log_path(effective_datadir, config_path))
    wallet_summary: dict[str, object] = {
        "summary_attempted": False,
        "summary_available": False,
        "account_count": None,
        "accounts": [],
        "note_counts": None,
        "operation_ids": None,
        "method_errors": {},
    }
    if http_url and probe and probe["status_code"] == 200:
        wallet_summary = build_wallet_summary(
            http_url,
            effective_http_user,
            password_info["password"],
            args.timeout,
            args.recent_transaction_limit,
        )

    notes: list[str] = []
    if live_process:
        if args.binary == "zallet" and effective_binary != args.binary:
            notes.append(f"Auto-discovered live wallet binary from process list: {effective_binary}.")
        if args.datadir is None and effective_datadir:
            notes.append(f"Auto-discovered live wallet datadir from process list: {effective_datadir}.")
    if args.http_user is None and inferred_http_user:
        notes.append(f"Inferred HTTP client user {inferred_http_user} from the sole rpc.auth entry.")
    if auth_entries and any(entry.get("has_pwhash") for entry in auth_entries):
        notes.append(
            "Server auth includes at least one pwhash entry; this is sufficient for server-side verification."
        )
    if auth_entries and not any(entry.get("has_password") for entry in auth_entries):
        notes.append(
            "Config auth appears hash-only; direct HTTP with env-backed credentials is the safer default."
        )
    if args.http_password_env and not password_info["env_present"]:
        if password_info["source"] == "keychain":
            notes.append(
                f"Environment variable {args.http_password_env} is not set; fell back to macOS Keychain."
            )
        else:
            notes.append(
                f"Environment variable {args.http_password_env} is not set, so authenticated HTTP probes may fail."
            )
    if password_info["source"] == "keychain":
        notes.append("HTTP password was resolved from macOS Keychain.")
    if (
        args.http_password_keychain_service
        and password_info["keychain_checked"]
        and not password_info["keychain_password_present"]
    ):
        detail = password_info["keychain_error"] or "item not found"
        notes.append(f"Keychain lookup failed: {detail}")
    if probe and probe["status_code"] == 401:
        notes.append("HTTP probe reached the server, but credentials were rejected or missing.")
    if probe and args.probe_method == "getwalletinfo" and looks_like_placeholder_getwalletinfo(
        probe.get("rpc_result")
    ):
        notes.append(
            "getwalletinfo appears to be placeholder-only in this build; use z_getbalances, z_listaccounts, z_getnotescount, z_listoperationids, and z_listtransactions for real wallet status."
        )

    return {
        "binary": {
            "requested": args.binary,
            "resolved_path": shutil.which(effective_binary) or effective_binary,
            "exists": shutil.which(effective_binary) is not None or Path(effective_binary).exists(),
            "supports_rpc_cli": binary_supports_rpc(effective_binary),
        },
        "live_process": live_process,
        "config": {
            "datadir": str(datadir_path) if datadir_path else None,
            "path": str(config_path) if config_path else None,
            "exists": bool(config_path and config_path.exists()),
            "rpc_binds": binds,
            "rpc_auth": auth_entries,
        },
        "log": log_status,
        "http": {
            "url": http_url,
            "client_user": effective_http_user,
            "client_user_inferred": args.http_user is None and effective_http_user is not None,
            "password_env": args.http_password_env,
            "password_env_present": password_info["env_present"],
            "password_source": password_info["source"],
            "password_keychain_service": password_info["keychain_service"],
            "password_keychain_account": password_info["keychain_account"],
            "password_keychain_present": password_info["keychain_password_present"],
            "password_keychain_error": password_info["keychain_error"],
            "probe_method": args.probe_method,
            "probe": probe,
        },
        "wallet": wallet_summary,
        "notes": notes,
    }


def render_text(status: dict[str, object], output_timezone) -> str:
    binary = status["binary"]
    config = status["config"]
    log = status["log"]
    http = status["http"]
    probe = http["probe"]
    wallet = status["wallet"]

    lines = [
        "Binary",
        f"- Requested: {binary['requested']}",
        f"- Resolved path: {binary['resolved_path']}",
        f"- Exists: {'yes' if binary['exists'] else 'no'}",
        f"- Supports `rpc` CLI subcommand: {'yes' if binary['supports_rpc_cli'] else 'no'}",
        "Config",
        f"- Datadir: {config['datadir'] or 'not inferred'}",
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
            "Log",
            f"- Path: {log['path'] or 'not inferred'}",
            f"- Exists: {'yes' if log['exists'] else 'no'}",
        ]
    )

    latest_chain_tip = log["latest_chain_tip"]
    if latest_chain_tip:
        lines.append(
            f"- Latest chain tip: {latest_chain_tip['height']} {latest_chain_tip['hash']}"
        )
        latest_chain_tip_time = render_timestamp(latest_chain_tip["log_time"], output_timezone)
        lines.append(f"- Latest chain tip log time: {latest_chain_tip_time or latest_chain_tip['log_time']}")
    else:
        lines.append("- Latest chain tip: not found")

    if log["recently_reached_chain_tip"] is None:
        lines.append("- Recently reached chain tip: unknown")
    else:
        lines.append(
            f"- Recently reached chain tip: {'yes' if log['recently_reached_chain_tip'] else 'no'}"
        )
        if log["latest_reached_chain_tip_log_time"]:
            reached_chain_tip_time = render_timestamp(
                log["latest_reached_chain_tip_log_time"],
                output_timezone,
            )
            lines.append(
                "- Latest reached-chain-tip log time: "
                f"{reached_chain_tip_time or log['latest_reached_chain_tip_log_time']}"
            )

    lines.extend(
        [
            "HTTP JSON-RPC",
            f"- URL: {http['url'] or 'not resolved'}",
            f"- Client user: {http['client_user'] or 'none'}",
            f"- Client user inferred: {'yes' if http['client_user_inferred'] else 'no'}",
            f"- Password env: {http['password_env'] or 'none'}",
            f"- Password env present: {'yes' if http['password_env_present'] else 'no'}",
            f"- Password keychain service: {http['password_keychain_service'] or 'none'}",
            f"- Password keychain account: {http['password_keychain_account'] or 'none'}",
            f"- Password keychain present: {'yes' if http['password_keychain_present'] else 'no'}",
            f"- Password source: {http['password_source'] or 'none'}",
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
        if http["password_keychain_error"]:
            lines.append(f"- Keychain lookup error: {http['password_keychain_error']}")

    lines.extend(
        [
            "Wallet Summary",
            f"- Summary attempted: {'yes' if wallet['summary_attempted'] else 'no'}",
            f"- Summary available: {'yes' if wallet['summary_available'] else 'no'}",
        ]
    )

    if wallet["account_count"] is not None:
        lines.append(f"- Account count: {wallet['account_count']}")

    if wallet["note_counts"] is None:
        lines.append("- Note counts: unavailable")
    else:
        lines.append(
            "- Note counts: "
            + ", ".join(
                f"{pool}={count}" for pool, count in sorted(wallet["note_counts"].items())
            )
        )

    if wallet["operation_ids"] is None:
        lines.append("- Pending operation IDs: unavailable")
    else:
        lines.append(
            f"- Pending operation IDs: {', '.join(wallet['operation_ids']) if wallet['operation_ids'] else 'none'}"
        )

    accounts = wallet["accounts"]
    if accounts:
        for account in accounts:
            account_name = account["name"] or account["account_uuid"]
            balance = account["spendable_balance_zec"]
            balance_desc = f"{balance} ZEC spendable" if balance is not None else "spendable balance unavailable"
            address_count = account["known_address_count"]
            if address_count is not None:
                balance_desc = f"{balance_desc}, {address_count} known addresses"

            recent_transactions = account["recent_transactions"]
            if recent_transactions:
                latest = recent_transactions[-1]
                amount = latest["absolute_balance_delta_zec"] or latest["account_balance_delta_zec"]
                latest_tx_time = render_timestamp(latest["block_datetime"], output_timezone)
                balance_desc = (
                    f"{balance_desc}, latest tx {latest['direction']} {amount} ZEC"
                    f" at {latest_tx_time or latest['block_datetime']}"
                )

            lines.append(f"- Account {account_name}: {balance_desc}")
    else:
        lines.append("- Accounts: none or unavailable")

    if wallet["method_errors"]:
        lines.append("Wallet Summary Method Errors")
        for method, detail in sorted(wallet["method_errors"].items()):
            lines.append(f"- {method}: {detail}")

    notes = status["notes"]
    if notes:
        lines.append("Notes")
        for note in notes:
            lines.append(f"- {note}")

    return "\n".join(lines)


def render_summary(status: dict[str, object], output_timezone) -> str:
    binary = status["binary"]
    config = status["config"]
    log = status["log"]
    http = status["http"]
    probe = http["probe"]
    wallet = status["wallet"]

    if probe and probe.get("status_code") == 200 and wallet["summary_available"]:
        headline = "Wallet status looks healthy."
    elif probe and probe.get("status_code") == 401:
        headline = "Wallet is running, but RPC auth failed."
    elif probe and probe.get("transport_error"):
        headline = "Wallet status is incomplete because the RPC probe failed."
    elif http["url"] is None:
        headline = "Wallet status is incomplete because no RPC bind was resolved."
    else:
        headline = "Wallet status is incomplete."

    lines = [headline, ""]

    live_binary = binary["resolved_path"] or binary["requested"]
    datadir = config["datadir"] or "unknown datadir"
    config_path = config["path"] or "unknown config path"
    rpc_url = http["url"] or "unknown RPC URL"
    client_user = http["client_user"] or "no user"
    auth_source = http["password_source"] or "no password source"
    transport = "direct HTTP JSON-RPC" if not binary["supports_rpc_cli"] else "HTTP JSON-RPC"
    lines.append(f"Binary: {live_binary}. Datadir: {datadir}. Config: {config_path}.")
    lines.append(
        f"RPC: {rpc_url} checked over {transport} as {client_user} via {auth_source}."
    )

    latest_chain_tip = log["latest_chain_tip"]
    sync_parts: list[str] = []
    if latest_chain_tip:
        latest_chain_tip_time = render_timestamp(latest_chain_tip["log_time"], output_timezone)
        sync_parts.append(
            f"latest observed tip {latest_chain_tip['height']} at "
            f"{latest_chain_tip_time or latest_chain_tip['log_time']}"
        )
    if log["latest_reached_chain_tip_log_time"]:
        reached_chain_tip_time = render_timestamp(
            log["latest_reached_chain_tip_log_time"],
            output_timezone,
        )
        sync_parts.append(
            "wallet logged reaching chain tip at "
            f"{reached_chain_tip_time or log['latest_reached_chain_tip_log_time']}"
        )
    if sync_parts:
        lines.append("Sync: " + "; ".join(sync_parts) + ".")

    account_summaries: list[str] = []
    for account in wallet["accounts"]:
        account_name = account["name"] or account["account_uuid"]
        parts: list[str] = []
        if account["spendable_balance_zec"] is not None:
            parts.append(f"{account['spendable_balance_zec']} ZEC spendable")
        if account["known_address_count"] is not None:
            parts.append(f"{account['known_address_count']} known addresses")
        account_summaries.append(f"{account_name}: {', '.join(parts) if parts else 'details unavailable'}")

    if wallet["account_count"] is not None:
        details = f" ({'; '.join(account_summaries)})" if account_summaries else ""
        lines.append(f"Accounts: {wallet['account_count']}{details}.")

    if wallet["note_counts"] is not None:
        note_counts = ", ".join(
            f"{pool}={count}" for pool, count in sorted(wallet["note_counts"].items())
        )
        lines.append(f"Notes: {note_counts}.")

    if wallet["operation_ids"] is not None:
        operations = ", ".join(wallet["operation_ids"]) if wallet["operation_ids"] else "none"
        lines.append(f"Pending operations: {operations}.")

    recent_activity: list[tuple[datetime, str]] = []
    for account in wallet["accounts"]:
        account_name = account["name"] or account["account_uuid"]
        for tx in account["recent_transactions"]:
            tx_time = parse_timestamp(tx["block_datetime"]) or datetime.min.replace(tzinfo=timezone.utc)
            rendered_tx_time = render_timestamp(tx["block_datetime"], output_timezone)
            amount = tx["absolute_balance_delta_zec"] or tx["account_balance_delta_zec"] or "unknown"
            recent_activity.append(
                (
                    tx_time,
                    f"- {rendered_tx_time or tx['block_datetime']}: {account_name} "
                    f"{tx['direction']} {amount} ZEC",
                )
            )

    if recent_activity:
        lines.append("Recent activity:")
        for _, item in sorted(recent_activity, key=lambda entry: entry[0]):
            lines.append(item)

    if wallet["method_errors"]:
        method_errors = ", ".join(
            f"{method}={detail}" for method, detail in sorted(wallet["method_errors"].items())
        )
        lines.append(f"Method errors: {method_errors}.")

    placeholder_note = next(
        (
            note
            for note in status["notes"]
            if "getwalletinfo appears to be placeholder-only" in note
        ),
        None,
    )
    if placeholder_note:
        lines.append(f"Alpha caveat: {placeholder_note}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    status = build_status(args)
    try:
        output_timezone = resolve_output_timezone(args.timezone)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.format == "json":
        json.dump(status, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    elif args.format == "summary":
        print(render_summary(status, output_timezone))
    else:
        print(render_text(status, output_timezone))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
