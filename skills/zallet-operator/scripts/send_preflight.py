#!/usr/bin/env python3
"""
Prepare a deterministic preflight summary for a Zallet z_sendmany request.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from zallet_rpc_util import (
    extract_rpc_binds,
    infer_http_url,
    json_rpc_request,
    load_toml_file,
    resolve_http_password,
    resolve_config_path,
)

ZAT_PER_ZEC = Decimal("100000000")


class RpcError(RuntimeError):
    pass


class RpcClient:
    def __init__(self, url: str, user: str | None, password: str | None, timeout: int) -> None:
        self.url = url
        self.user = user
        self.password = password
        self.timeout = timeout

    def call(self, method: str, params: list[Any]) -> Any:
        response = json_rpc_request(
            self.url,
            method,
            params,
            timeout=self.timeout,
            user=self.user,
            password=self.password,
        )
        if response["transport_error"]:
            raise RpcError(f"{method} transport failure: {response['transport_error']}")
        if response["rpc_error"] is not None:
            raise RpcError(f"{method} RPC error: {json.dumps(response['rpc_error'], sort_keys=True)}")
        return response["rpc_result"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize source, recipients, balance, and wallet state before z_sendmany."
    )
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
    parser.add_argument("--timeout", type=int, default=10, help="HTTP timeout in seconds.")
    parser.add_argument(
        "--minconf",
        type=int,
        default=1,
        help="Minimum confirmations for balance checks.",
    )
    parser.add_argument(
        "--from",
        dest="source_identifier",
        required=True,
        help="Source account name, account UUID, or source address.",
    )
    parser.add_argument("--recipients-json", help="JSON array of recipient objects.")
    parser.add_argument("--recipients-file", help="Path to a JSON file containing recipients.")
    parser.add_argument(
        "--privacy-policy",
        default="FullPrivacy",
        help="Privacy policy string for the intended z_sendmany call.",
    )
    parser.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Output format.",
    )
    return parser.parse_args()


def load_recipients_input(args: argparse.Namespace) -> str:
    if args.recipients_json and args.recipients_file:
        raise ValueError("pass either --recipients-json or --recipients-file, not both")
    if args.recipients_file:
        return Path(args.recipients_file).read_text(encoding="utf-8")
    if args.recipients_json:
        return args.recipients_json
    raise ValueError("one of --recipients-json or --recipients-file is required")


def amount_to_zat(value: Any) -> int:
    if isinstance(value, (int, float, str)):
        text = str(value)
    else:
        raise ValueError("amount must be a string or number")

    try:
        amount = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {text}") from exc

    if not amount.is_finite() or amount <= 0:
        raise ValueError("amount must be positive and finite")
    if amount.as_tuple().exponent < -8:
        raise ValueError("amount must have at most 8 decimal places")

    return int(amount * ZAT_PER_ZEC)


def format_zec(zat: int) -> str:
    return f"{(Decimal(zat) / ZAT_PER_ZEC):.8f}"


def parse_recipients(raw: str) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid recipients JSON: {exc}") from exc

    if not isinstance(decoded, list) or not decoded:
        raise ValueError("recipients input must be a non-empty JSON array")

    recipients: list[dict[str, Any]] = []
    seen_addresses: set[str] = set()
    for entry in decoded:
        if not isinstance(entry, dict):
            raise ValueError("each recipient must be a JSON object")

        address = entry.get("address")
        memo = entry.get("memo")
        if not isinstance(address, str) or not address:
            raise ValueError("each recipient requires a non-empty string address")
        if memo is not None and not isinstance(memo, str):
            raise ValueError("memo must be a string when present")
        if address in seen_addresses:
            raise ValueError(f"duplicate recipient address: {address}")

        amount_zat = amount_to_zat(entry.get("amount"))
        recipients.append(
            {
                "address": address,
                "amount": format_zec(amount_zat),
                "amount_zat": amount_zat,
                "memo": memo,
                "memo_present": memo is not None,
            }
        )
        seen_addresses.add(address)

    return recipients


def choose_default_from_address(account: dict[str, Any]) -> tuple[str, str, int | None]:
    addresses = account.get("addresses")
    if not isinstance(addresses, list):
        raise ValueError("account does not include address inventory")

    for field in ("ua", "sapling", "transparent"):
        for entry in addresses:
            if not isinstance(entry, dict):
                continue
            value = entry.get(field)
            if isinstance(value, str) and value:
                diversifier_index = entry.get("diversifier_index")
                return value, field, diversifier_index if isinstance(diversifier_index, int) else None

    raise ValueError("account has no spendable-looking source address")


def resolve_source(accounts: list[dict[str, Any]], source_identifier: str) -> dict[str, Any]:
    named_matches = [
        account
        for account in accounts
        if account.get("name") == source_identifier
        or account.get("account_uuid") == source_identifier
    ]
    if len(named_matches) > 1:
        raise ValueError(f"source identifier is ambiguous: {source_identifier}")
    if len(named_matches) == 1:
        account = named_matches[0]
        from_address, address_kind, diversifier_index = choose_default_from_address(account)
        return {
            "input": source_identifier,
            "resolution": "account",
            "account_uuid": account.get("account_uuid"),
            "account_name": account.get("name"),
            "known_address_count": len(account.get("addresses", [])),
            "from_address": from_address,
            "from_address_kind": address_kind,
            "diversifier_index": diversifier_index,
        }

    for account in accounts:
        for entry in account.get("addresses", []):
            if not isinstance(entry, dict):
                continue
            for field in ("ua", "sapling", "transparent"):
                if entry.get(field) == source_identifier:
                    diversifier_index = entry.get("diversifier_index")
                    return {
                        "input": source_identifier,
                        "resolution": "address",
                        "account_uuid": account.get("account_uuid"),
                        "account_name": account.get("name"),
                        "known_address_count": len(account.get("addresses", [])),
                        "from_address": source_identifier,
                        "from_address_kind": field,
                        "diversifier_index": diversifier_index if isinstance(diversifier_index, int) else None,
                    }

    raise ValueError(f"could not resolve source account or address: {source_identifier}")


def account_spendable_zat(balances: dict[str, Any], account_uuid: str) -> int:
    accounts = balances.get("accounts")
    if not isinstance(accounts, list):
        return 0

    for account in accounts:
        if not isinstance(account, dict) or account.get("account_uuid") != account_uuid:
            continue
        total = account.get("total")
        if not isinstance(total, dict):
            return 0
        spendable = total.get("spendable")
        if not isinstance(spendable, dict):
            return 0
        value_zat = spendable.get("valueZat")
        return value_zat if isinstance(value_zat, int) else 0

    return 0


def validate_recipient(client: RpcClient, recipient: dict[str, Any]) -> dict[str, Any]:
    address = recipient["address"]
    if address.startswith("u"):
        receivers = client.call("z_listunifiedreceivers", [address])
        return {
            "kind": "unified",
            "validated": True,
            "receivers": {
                "orchard": "orchard" in receivers,
                "sapling": "sapling" in receivers,
                "p2pkh": "p2pkh" in receivers,
                "p2sh": "p2sh" in receivers,
            },
        }

    if address.startswith("t"):
        result = client.call("validateaddress", [address])
        return {
            "kind": "transparent",
            "validated": bool(result.get("isvalid")),
            "details": result,
        }

    return {
        "kind": "shielded_or_other",
        "validated": None,
        "details": "No stable generic validation RPC is available for this address kind.",
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    config_path = resolve_config_path(args.datadir, args.config)
    config_data = load_toml_file(config_path)
    http_url = infer_http_url(args.http_url, extract_rpc_binds(config_data))
    if not http_url:
        raise ValueError("could not determine HTTP JSON-RPC URL from args or config")

    password_info = resolve_http_password(
        password_env=args.http_password_env,
        keychain_service=args.http_password_keychain_service,
        keychain_account=args.http_password_keychain_account,
        default_keychain_account=args.http_user,
    )
    if args.http_user and password_info["source"] is None and (
        args.http_password_env or args.http_password_keychain_service
    ):
        failures = []
        if args.http_password_env and not password_info["env_present"]:
            failures.append(f"environment variable {args.http_password_env} is not set")
        if args.http_password_keychain_service and not password_info["keychain_password_present"]:
            detail = password_info["keychain_error"] or "item not found"
            failures.append(f"Keychain lookup failed: {detail}")
        raise ValueError("; ".join(failures))

    client = RpcClient(http_url, args.http_user, password_info["password"], args.timeout)
    recipients = parse_recipients(load_recipients_input(args))
    accounts = client.call("z_listaccounts", [True])
    if not isinstance(accounts, list):
        raise RpcError("z_listaccounts returned an unexpected shape")

    source = resolve_source(accounts, args.source_identifier)
    balances = client.call("z_getbalances", [args.minconf])
    if not isinstance(balances, dict):
        raise RpcError("z_getbalances returned an unexpected shape")

    operations = client.call("z_listoperationids", [])
    if not isinstance(operations, list):
        raise RpcError("z_listoperationids returned an unexpected shape")

    wallet_info = client.call("getwalletinfo", [])
    if not isinstance(wallet_info, dict):
        wallet_info = {}

    validated_recipients = []
    total_recipient_zat = 0
    warnings: list[str] = []
    for recipient in recipients:
        total_recipient_zat += recipient["amount_zat"]
        recipient["validation"] = validate_recipient(client, recipient)
        validated_recipients.append(recipient)
        if recipient["validation"]["validated"] is False:
            warnings.append(f"recipient did not validate cleanly: {recipient['address']}")
        if recipient["validation"]["validated"] is None:
            warnings.append(
                f"recipient validation is partial for address kind {recipient['validation']['kind']}: {recipient['address']}"
            )

    spendable_zat = account_spendable_zat(balances, str(source["account_uuid"]))
    if spendable_zat < total_recipient_zat:
        warnings.append("account spendable balance is lower than the requested send total")
    if operations:
        warnings.append("wallet has pending async operations; inspect them before sending again")

    unlocked_until = wallet_info.get("unlocked_until")
    wallet_encrypted = unlocked_until is not None
    wallet_unlocked = None
    if isinstance(unlocked_until, int):
        wallet_unlocked = unlocked_until > 0
        if not wallet_unlocked:
            warnings.append("wallet appears locked; user may need to unlock it locally before spending")

    return {
        "source": source,
        "recipients": validated_recipients,
        "privacy_policy": args.privacy_policy,
        "minconf": args.minconf,
        "balances": {
            "account_spendable_zat": spendable_zat,
            "account_spendable": format_zec(spendable_zat),
            "requested_total_zat": total_recipient_zat,
            "requested_total": format_zec(total_recipient_zat),
        },
        "wallet_state": {
            "pending_operation_count": len(operations),
            "pending_operations": operations,
            "wallet_encrypted": wallet_encrypted,
            "wallet_unlocked": wallet_unlocked,
            "unlocked_until": unlocked_until if isinstance(unlocked_until, int) else None,
        },
        "transport": {
            "http_url": http_url,
            "http_user": args.http_user,
            "password_env": args.http_password_env,
            "password_source": password_info["source"],
            "password_keychain_service": password_info["keychain_service"],
            "password_keychain_account": password_info["keychain_account"],
        },
        "warnings": warnings,
    }


def render_text(report: dict[str, Any]) -> str:
    source = report["source"]
    balances = report["balances"]
    wallet_state = report["wallet_state"]

    lines = [
        "Send preflight",
        f"- Source input: {source['input']}",
        f"- Source resolution: {source['resolution']}",
        f"- Source account: {source.get('account_name') or '<unnamed>'}",
        f"- Source account UUID: {source['account_uuid']}",
        f"- Chosen fromaddress: {source['from_address']}",
        f"- Chosen fromaddress kind: {source['from_address_kind']}",
        f"- Known addresses in account: {source['known_address_count']}",
        f"- Spendable account balance: {balances['account_spendable']} ZEC",
        f"- Requested send total: {balances['requested_total']} ZEC",
        f"- Privacy policy: {report['privacy_policy']}",
        f"- Pending operations: {wallet_state['pending_operation_count']}",
        f"- Password source: {report['transport']['password_source'] or 'none'}",
    ]

    if wallet_state["wallet_encrypted"]:
        lines.append(f"- Wallet unlocked: {'yes' if wallet_state['wallet_unlocked'] else 'no'}")

    lines.append("Recipients")
    for idx, recipient in enumerate(report["recipients"], start=1):
        validation = recipient["validation"]
        status = (
            "validated"
            if validation["validated"] is True
            else "not fully validated"
            if validation["validated"] is None
            else "invalid"
        )
        lines.append(
            f"- {idx}. {recipient['address']} amount={recipient['amount']} memo={'yes' if recipient['memo_present'] else 'no'} kind={validation['kind']} status={status}"
        )

    if report["warnings"]:
        lines.append("Warnings")
        for warning in report["warnings"]:
            lines.append(f"- {warning}")

    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    try:
        report = build_report(args)
    except (OSError, RpcError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.format == "json":
        json.dump(report, sys.stdout, sort_keys=True)
        sys.stdout.write("\n")
    else:
        print(render_text(report))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
