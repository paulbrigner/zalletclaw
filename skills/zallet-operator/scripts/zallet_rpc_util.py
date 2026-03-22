#!/usr/bin/env python3
"""
Shared helpers for Zallet skill scripts.
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
from pathlib import Path
from typing import Any
from urllib import error, request

try:
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:
    tomllib = None  # type: ignore[assignment]


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


def resolve_config_path(datadir: str | None, config: str | None) -> Path | None:
    if config:
        return Path(config).expanduser().resolve()

    if datadir:
        return Path(datadir).expanduser().resolve() / "zallet.toml"

    return None


def load_toml_file(path: Path | None) -> dict[str, Any] | None:
    if path is None or not path.exists():
        return None

    if tomllib is not None:
        with path.open("rb") as handle:
            data = tomllib.load(handle)
        return data if isinstance(data, dict) else None

    return parse_minimal_toml(path.read_text(encoding="utf-8"))


def extract_rpc_binds(config_data: dict[str, Any] | None) -> list[str]:
    if not isinstance(config_data, dict):
        return []

    rpc_section = config_data.get("rpc")
    if not isinstance(rpc_section, dict):
        return []

    bind = rpc_section.get("bind")
    if isinstance(bind, str):
        return [bind]
    if isinstance(bind, list):
        return [item for item in bind if isinstance(item, str)]

    return []


def extract_rpc_auth(config_data: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(config_data, dict):
        return []

    rpc_section = config_data.get("rpc")
    if not isinstance(rpc_section, dict):
        return []

    auth_entries = rpc_section.get("auth")
    if not isinstance(auth_entries, list):
        return []

    summary: list[dict[str, Any]] = []
    for entry in auth_entries:
        if not isinstance(entry, dict):
            continue

        summary.append(
            {
                "user": entry.get("user"),
                "has_password": bool(entry.get("password")),
                "has_pwhash": bool(entry.get("pwhash")),
            }
        )

    return summary


def infer_http_url(http_url: str | None, binds: list[str]) -> str | None:
    if http_url:
        return http_url

    if not binds:
        return None

    bind = binds[0]
    return bind if "://" in bind else f"http://{bind}"


def parse_json_bytes(raw: bytes) -> tuple[Any | None, str | None]:
    text = raw.decode("utf-8", errors="replace")
    if not text.strip():
        return None, None

    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def parse_minimal_toml(text: str) -> dict[str, Any]:
    """
    Fallback parser for the small subset of TOML fields this skill needs when tomllib is absent.
    """
    data: dict[str, Any] = {"rpc": {"auth": []}}
    current_section: str | None = None
    current_auth: dict[str, Any] | None = None

    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue

        if line == "[rpc]":
            current_section = "rpc"
            current_auth = None
            continue

        if line == "[[rpc.auth]]":
            current_section = "rpc.auth"
            current_auth = {}
            data.setdefault("rpc", {}).setdefault("auth", []).append(current_auth)
            continue

        if "=" not in line:
            continue

        key, raw_value = (part.strip() for part in line.split("=", 1))
        value = parse_minimal_toml_value(raw_value)

        if current_section == "rpc":
            data.setdefault("rpc", {})[key] = value
        elif current_section == "rpc.auth" and current_auth is not None:
            current_auth[key] = value

    return data


def parse_minimal_toml_value(raw_value: str) -> Any:
    if raw_value.startswith('"') or raw_value.startswith("["):
        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    if raw_value in ("true", "false"):
        return raw_value == "true"

    return raw_value


def json_rpc_request(
    url: str,
    method: str,
    params: list[Any],
    timeout: int = 10,
    user: str | None = None,
    password: str | None = None,
) -> dict[str, Any]:
    payload = json.dumps(
        {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")

    req = request.Request(
        url,
        data=payload,
        headers={"content-type": "application/json"},
        method="POST",
    )

    if user is not None and password is not None:
        token = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        req.add_header("Authorization", f"Basic {token}")

    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            body, json_error = parse_json_bytes(raw)
            return {
                "http_ok": True,
                "status_code": response.status,
                "body": body,
                "json_error": json_error,
                "transport_error": None,
                "rpc_result": body.get("result") if isinstance(body, dict) else None,
                "rpc_error": body.get("error") if isinstance(body, dict) else None,
            }
    except error.HTTPError as exc:
        raw = exc.read()
        body, json_error = parse_json_bytes(raw)
        return {
            "http_ok": False,
            "status_code": exc.code,
            "body": body,
            "json_error": json_error,
            "transport_error": str(exc),
            "rpc_result": body.get("result") if isinstance(body, dict) else None,
            "rpc_error": body.get("error") if isinstance(body, dict) else None,
        }
    except error.URLError as exc:
        return {
            "http_ok": False,
            "status_code": None,
            "body": None,
            "json_error": None,
            "transport_error": str(exc.reason),
            "rpc_result": None,
            "rpc_error": None,
        }
