from __future__ import annotations

import argparse
import importlib.util
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "zallet-operator" / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_rpc_command = load_module("build_rpc_command", SCRIPTS_DIR / "build_rpc_command.py")
send_preflight = load_module("send_preflight", SCRIPTS_DIR / "send_preflight.py")
zallet_rpc_util = load_module("zallet_rpc_util", SCRIPTS_DIR / "zallet_rpc_util.py")


class BuildRpcCommandTests(unittest.TestCase):
    def test_render_shell_injects_http_auth_env(self) -> None:
        rendered = build_rpc_command.render_shell(
            "http",
            ["curl", "-sS", "http://127.0.0.1:28232"],
            "alice",
            "RPC_PASSWORD",
        )
        self.assertIn('-u "alice:${RPC_PASSWORD}"', rendered)

    def test_choose_transport_auto_falls_back_to_http(self) -> None:
        args = argparse.Namespace(transport="auto", binary="/definitely/missing/zallet")
        self.assertEqual(build_rpc_command.choose_transport(args), "http")

    def test_binary_supports_rpc_from_help_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            script = Path(tmpdir) / "zallet"
            script.write_text(
                textwrap.dedent(
                    """\
                    #!/bin/sh
                    echo "Commands:"
                    echo "  start"
                    echo "  rpc"
                    """
                ),
                encoding="utf-8",
            )
            script.chmod(0o755)
            self.assertTrue(zallet_rpc_util.binary_supports_rpc(str(script)))


class SharedUtilTests(unittest.TestCase):
    def test_extract_rpc_auth_summary(self) -> None:
        config = {
            "rpc": {
                "auth": [
                    {"user": "hash-only", "pwhash": "abc"},
                    {"user": "plain", "password": "secret"},
                ]
            }
        }
        summary = zallet_rpc_util.extract_rpc_auth(config)
        self.assertEqual(summary[0]["user"], "hash-only")
        self.assertTrue(summary[0]["has_pwhash"])
        self.assertFalse(summary[0]["has_password"])
        self.assertTrue(summary[1]["has_password"])

    def test_infer_http_url_from_bind(self) -> None:
        self.assertEqual(
            zallet_rpc_util.infer_http_url(None, ["127.0.0.1:28232"]),
            "http://127.0.0.1:28232",
        )


class SendPreflightTests(unittest.TestCase):
    def test_parse_recipients_rejects_duplicate_addresses(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate recipient address"):
            send_preflight.parse_recipients(
                '[{"address":"u1abc","amount":"0.1"},{"address":"u1abc","amount":"0.2"}]'
            )

    def test_parse_recipients_formats_amounts(self) -> None:
        recipients = send_preflight.parse_recipients(
            '[{"address":"u1abc","amount":"0.001","memo":"6869"}]'
        )
        self.assertEqual(recipients[0]["amount_zat"], 100000)
        self.assertEqual(recipients[0]["amount"], "0.00100000")
        self.assertTrue(recipients[0]["memo_present"])

    def test_choose_default_from_address_prefers_unified(self) -> None:
        account = {
            "addresses": [
                {"sapling": "zs1example"},
                {"ua": "u1example", "diversifier_index": 7},
                {"transparent": "t1example"},
            ]
        }
        address, kind, diversifier_index = send_preflight.choose_default_from_address(account)
        self.assertEqual(address, "u1example")
        self.assertEqual(kind, "ua")
        self.assertEqual(diversifier_index, 7)

    def test_resolve_source_by_name(self) -> None:
        accounts = [
            {
                "account_uuid": "uuid-1",
                "name": "main",
                "addresses": [{"ua": "u1example", "diversifier_index": 1}],
            }
        ]
        source = send_preflight.resolve_source(accounts, "main")
        self.assertEqual(source["account_uuid"], "uuid-1")
        self.assertEqual(source["from_address"], "u1example")
        self.assertEqual(source["resolution"], "account")


if __name__ == "__main__":
    unittest.main()
