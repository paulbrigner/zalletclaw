from __future__ import annotations

import argparse
import importlib.util
import subprocess
import tempfile
import textwrap
import unittest
from unittest import mock
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "zallet-operator" / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


build_rpc_command = load_module("build_rpc_command", SCRIPTS_DIR / "build_rpc_command.py")
check_wallet_status = load_module("check_wallet_status", SCRIPTS_DIR / "check_wallet_status.py")
send_preflight = load_module("send_preflight", SCRIPTS_DIR / "send_preflight.py")
zallet_rpc_util = load_module("zallet_rpc_util", SCRIPTS_DIR / "zallet_rpc_util.py")


class BuildRpcCommandTests(unittest.TestCase):
    def test_render_shell_injects_http_auth_env(self) -> None:
        rendered = build_rpc_command.render_shell(
            "http",
            ["curl", "-sS", "http://127.0.0.1:28232"],
            "alice",
            "RPC_PASSWORD",
            None,
            None,
        )
        self.assertIn('-u "alice:${RPC_PASSWORD}"', rendered)

    def test_render_shell_injects_keychain_lookup(self) -> None:
        rendered = build_rpc_command.render_shell(
            "http",
            ["curl", "-sS", "http://127.0.0.1:28232"],
            "alice",
            None,
            "zallet-rpc",
            "alice",
        )
        self.assertIn(
            "security find-generic-password -s zallet-rpc -a alice -w",
            rendered,
        )

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

    def test_resolve_http_password_prefers_env(self) -> None:
        with mock.patch.dict("os.environ", {"RPC_PASSWORD": "env-secret"}, clear=True):
            with mock.patch.object(
                zallet_rpc_util,
                "lookup_keychain_password",
                return_value=("keychain-secret", None),
            ) as mocked_lookup:
                result = zallet_rpc_util.resolve_http_password(
                    password_env="RPC_PASSWORD",
                    keychain_service="zallet-rpc",
                    keychain_account="alice",
                )

        self.assertEqual(result["source"], "env")
        self.assertEqual(result["password"], "env-secret")
        mocked_lookup.assert_not_called()

    def test_resolve_http_password_falls_back_to_keychain(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(
                zallet_rpc_util,
                "lookup_keychain_password",
                return_value=("keychain-secret", None),
            ) as mocked_lookup:
                result = zallet_rpc_util.resolve_http_password(
                    password_env="RPC_PASSWORD",
                    keychain_service="zallet-rpc",
                    default_keychain_account="alice",
                )

        self.assertEqual(result["source"], "keychain")
        self.assertEqual(result["password"], "keychain-secret")
        mocked_lookup.assert_called_once_with("zallet-rpc", "alice")

    def test_resolve_http_password_auto_uses_default_macos_keychain_service(self) -> None:
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch.object(zallet_rpc_util.platform, "system", return_value="Darwin"), mock.patch.object(
                zallet_rpc_util,
                "lookup_keychain_password",
                return_value=("keychain-secret", None),
            ) as mocked_lookup:
                result = zallet_rpc_util.resolve_http_password(default_keychain_account="alice")

        self.assertEqual(result["source"], "keychain")
        self.assertEqual(result["keychain_service"], "zallet-rpc")
        mocked_lookup.assert_called_once_with("zallet-rpc", "alice")


class CheckWalletStatusTests(unittest.TestCase):
    def test_infer_http_user_from_sole_auth_entry(self) -> None:
        auth_entries = [{"user": "localcheck", "has_pwhash": True, "has_password": False}]
        self.assertEqual(check_wallet_status.infer_http_user(auth_entries), "localcheck")

    def test_discover_live_wallet_process_from_ps_output(self) -> None:
        ps_output = """USER PID %CPU %MEM VSZ RSS TTY STAT STARTED TIME COMMAND\npaul 30617 0.1 0.2 123 456 ?? SN 9:30PM 0:01 /Users/paul/dev/zallet/zallet -d .zallet start\n"""
        completed = subprocess.CompletedProcess(args=["ps", "aux"], returncode=0, stdout=ps_output, stderr="")

        with mock.patch.object(check_wallet_status.subprocess, "run", return_value=completed):
            discovered = check_wallet_status.discover_live_wallet_process()

        assert discovered is not None
        self.assertEqual(discovered["binary"], "/Users/paul/dev/zallet/zallet")
        self.assertEqual(discovered["datadir"], "/Users/paul/dev/zallet/.zallet")

    def test_discover_live_wallet_process_resolves_relative_datadir_via_search(self) -> None:
        ps_output = """USER PID %CPU %MEM VSZ RSS TTY STAT STARTED TIME COMMAND\npaul 30617 0.1 0.2 123 456 ?? SN 9:30PM 0:01 zallet -d .zallet start\n"""
        completed = subprocess.CompletedProcess(args=["ps", "aux"], returncode=0, stdout=ps_output, stderr="")

        with mock.patch.object(check_wallet_status.subprocess, "run", return_value=completed), mock.patch.object(
            check_wallet_status,
            "resolve_relative_live_datadir",
            return_value="/Users/paul/dev/zallet/.zallet",
        ):
            discovered = check_wallet_status.discover_live_wallet_process()

        assert discovered is not None
        self.assertEqual(discovered["binary"], "zallet")
        self.assertEqual(discovered["datadir"], "/Users/paul/dev/zallet/.zallet")

    def test_build_status_auto_discovers_binary_and_datadir(self) -> None:
        args = argparse.Namespace(
            binary="zallet",
            datadir=None,
            config=None,
            http_url=None,
            http_user=None,
            http_password_env=None,
            http_password_keychain_service=None,
            http_password_keychain_account=None,
            probe_method="getwalletinfo",
            recent_transaction_limit=3,
            timeout=5,
            format="json",
            timezone="utc",
        )

        with mock.patch.object(
            check_wallet_status,
            "discover_live_wallet_process",
            return_value={
                "command": "/Users/paul/dev/zallet/zallet -d .zallet start",
                "argv": ["/Users/paul/dev/zallet/zallet", "-d", ".zallet", "start"],
                "binary": "/Users/paul/dev/zallet/zallet",
                "datadir": "/Users/paul/dev/zallet/.zallet",
            },
        ), mock.patch.object(
            check_wallet_status,
            "resolve_config_path",
            return_value=Path("/Users/paul/dev/zallet/.zallet/zallet.toml"),
        ), mock.patch.object(
            check_wallet_status,
            "resolve_datadir_path",
            return_value=Path("/Users/paul/dev/zallet/.zallet"),
        ), mock.patch.object(
            check_wallet_status,
            "load_toml_file",
            return_value={"rpc": {"bind": "127.0.0.1:28232", "auth": [{"user": "localcheck", "pwhash": "abc"}]}}
        ), mock.patch.object(
            check_wallet_status,
            "read_log_status",
            return_value={
                "path": "/Users/paul/dev/zallet/.zallet/zallet.log",
                "exists": True,
                "latest_chain_tip": None,
                "recently_reached_chain_tip": False,
                "latest_reached_chain_tip_log_time": None,
            },
        ), mock.patch.object(
            check_wallet_status,
            "json_rpc_request",
            return_value={
                "http_ok": True,
                "status_code": 200,
                "rpc_error": None,
                "rpc_result": {"walletversion": 0, "mnemonic_seedfp": "TODO", "txcount": 0},
                "transport_error": None,
            },
        ), mock.patch.object(
            check_wallet_status,
            "build_wallet_summary",
            return_value={
                "summary_attempted": True,
                "summary_available": False,
                "account_count": 0,
                "accounts": [],
                "note_counts": None,
                "operation_ids": [],
                "method_errors": {},
            },
        ), mock.patch.object(
            check_wallet_status,
            "binary_supports_rpc",
            return_value=False,
        ):
            status = check_wallet_status.build_status(args)

        self.assertEqual(status["binary"]["resolved_path"], "/Users/paul/dev/zallet/zallet")
        self.assertEqual(status["config"]["datadir"], "/Users/paul/dev/zallet/.zallet")
        self.assertTrue(any("Auto-discovered live wallet binary" in note for note in status["notes"]))
        self.assertTrue(any("Auto-discovered live wallet datadir" in note for note in status["notes"]))

    def test_build_wallet_summary_collects_balances_and_recent_transactions(self) -> None:
        def fake_json_rpc_request(url, method, params, timeout, user, password):
            self.assertEqual(url, "http://127.0.0.1:28232")
            self.assertEqual(user, "alice")
            self.assertEqual(password, "pw")
            if method == "z_listaccounts":
                return {
                    "http_ok": True,
                    "status_code": 200,
                    "rpc_error": None,
                    "rpc_result": [
                        {
                            "account_uuid": "uuid-1",
                            "name": "main",
                            "seedfp": "seedfp",
                            "zip32_account_index": 0,
                            "addresses": [{"ua": "u1a"}, {"ua": "u1b"}],
                        }
                    ],
                }
            if method == "z_getbalances":
                return {
                    "http_ok": True,
                    "status_code": 200,
                    "rpc_error": None,
                    "rpc_result": {
                        "accounts": [
                            {
                                "account_uuid": "uuid-1",
                                "total": {"spendable": {"valueZat": 12345678}},
                            }
                        ]
                    },
                }
            if method == "z_getnotescount":
                return {
                    "http_ok": True,
                    "status_code": 200,
                    "rpc_error": None,
                    "rpc_result": {"orchard": 2, "sapling": 0, "sprout": 0},
                }
            if method == "z_listoperationids":
                return {
                    "http_ok": True,
                    "status_code": 200,
                    "rpc_error": None,
                    "rpc_result": ["op-1"],
                }
            if method == "z_listtransactions":
                self.assertEqual(params, ["uuid-1", None, None, 0, 100])
                return {
                    "http_ok": True,
                    "status_code": 200,
                    "rpc_error": None,
                    "rpc_result": [
                        {
                            "account_balance_delta": 200000,
                            "block_datetime": "2026-03-20T10:00:00Z",
                            "block_time": 100,
                            "expired_unmined": False,
                            "mined_height": 10,
                            "received_note_count": 1,
                            "sent_note_count": 0,
                            "txid": "tx-1",
                        },
                        {
                            "account_balance_delta": -110000,
                            "block_datetime": "2026-03-22T14:14:06Z",
                            "block_time": 200,
                            "expired_unmined": False,
                            "mined_height": 20,
                            "received_note_count": 0,
                            "sent_note_count": 1,
                            "txid": "tx-2",
                        },
                    ],
                }
            raise AssertionError(f"Unexpected method {method}")

        with mock.patch.object(check_wallet_status, "json_rpc_request", side_effect=fake_json_rpc_request):
            summary = check_wallet_status.build_wallet_summary(
                "http://127.0.0.1:28232",
                "alice",
                "pw",
                5,
                2,
            )

        self.assertTrue(summary["summary_available"])
        self.assertEqual(summary["account_count"], 1)
        self.assertEqual(summary["operation_ids"], ["op-1"])
        self.assertEqual(summary["note_counts"]["orchard"], 2)
        account = summary["accounts"][0]
        self.assertEqual(account["name"], "main")
        self.assertEqual(account["known_address_count"], 2)
        self.assertEqual(account["spendable_balance_zec"], "0.12345678")
        self.assertEqual(account["recent_transactions"][-1]["direction"], "sent")
        self.assertEqual(account["recent_transactions"][-1]["absolute_balance_delta_zec"], "0.00110000")

    def test_read_log_status_extracts_chain_tip(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "zallet.log"
            log_path.write_text(
                textwrap.dedent(
                    """\
                    \x1b[2m2026-03-22T20:17:33.121430Z\x1b[0m INFO steady_state: Reached chain tip, streaming mempool
                    \x1b[2m2026-03-22T20:17:33.193802Z\x1b[0m INFO steady_state: New chain tip: 3281708 0000000000330e28fe8b84cafb75b6bbbe1fec016bda4224fa32217de49cf57d
                    """
                ),
                encoding="utf-8",
            )

            status = check_wallet_status.read_log_status(log_path)

        self.assertTrue(status["exists"])
        self.assertTrue(status["recently_reached_chain_tip"])
        self.assertEqual(status["latest_chain_tip"]["height"], 3281708)

    def test_render_text_localizes_timestamps(self) -> None:
        status = {
            "binary": {
                "requested": "/path/to/zallet",
                "resolved_path": "/path/to/zallet",
                "exists": True,
                "supports_rpc_cli": False,
            },
            "config": {
                "datadir": "/wallet",
                "path": "/wallet/zallet.toml",
                "exists": True,
                "rpc_binds": ["127.0.0.1:28232"],
                "rpc_auth": [{"user": "localcheck", "has_password": False, "has_pwhash": True}],
            },
            "log": {
                "path": "/wallet/zallet.log",
                "exists": True,
                "latest_chain_tip": {
                    "height": 3281739,
                    "hash": "abc123",
                    "log_time": "2026-03-22T20:53:37.972636Z",
                },
                "recently_reached_chain_tip": True,
                "latest_reached_chain_tip_log_time": "2026-03-22T20:53:37.974719Z",
            },
            "http": {
                "url": "http://127.0.0.1:28232",
                "client_user": "localcheck",
                "client_user_inferred": True,
                "password_env": None,
                "password_env_present": None,
                "password_source": "keychain",
                "password_keychain_service": "zallet-rpc",
                "password_keychain_account": "localcheck",
                "password_keychain_present": True,
                "password_keychain_error": None,
                "probe_method": "getwalletinfo",
                "probe": {"status_code": 200, "http_ok": True, "rpc_error": None, "transport_error": None},
            },
            "wallet": {
                "summary_attempted": True,
                "summary_available": True,
                "account_count": 1,
                "accounts": [
                    {
                        "account_uuid": "uuid-1",
                        "name": "main",
                        "known_address_count": 40,
                        "spendable_balance_zec": "0.11271754",
                        "recent_transactions": [
                            {
                                "block_datetime": "2026-03-22T14:14:06Z",
                                "direction": "sent",
                                "absolute_balance_delta_zec": "0.00110000",
                                "account_balance_delta_zec": "-0.00110000",
                            }
                        ],
                    }
                ],
                "note_counts": {"orchard": 19, "sapling": 0, "sprout": 0},
                "operation_ids": [],
                "method_errors": {},
            },
            "notes": [],
        }

        rendered = check_wallet_status.render_text(
            status,
            check_wallet_status.resolve_output_timezone("America/New_York"),
        )

        self.assertIn("2026-03-22 04:53:37 PM EDT", rendered)
        self.assertIn("2026-03-22 10:14:06 AM EDT", rendered)

    def test_render_summary_includes_localized_recent_activity(self) -> None:
        status = {
            "binary": {
                "requested": "/path/to/zallet",
                "resolved_path": "/path/to/zallet",
                "exists": True,
                "supports_rpc_cli": False,
            },
            "config": {
                "datadir": "/wallet",
                "path": "/wallet/zallet.toml",
                "exists": True,
                "rpc_binds": ["127.0.0.1:28232"],
                "rpc_auth": [{"user": "localcheck", "has_password": False, "has_pwhash": True}],
            },
            "log": {
                "path": "/wallet/zallet.log",
                "exists": True,
                "latest_chain_tip": {
                    "height": 3281739,
                    "hash": "abc123",
                    "log_time": "2026-03-22T20:53:37.972636Z",
                },
                "recently_reached_chain_tip": True,
                "latest_reached_chain_tip_log_time": "2026-03-22T20:53:37.974719Z",
            },
            "http": {
                "url": "http://127.0.0.1:28232",
                "client_user": "localcheck",
                "client_user_inferred": True,
                "password_env": None,
                "password_env_present": None,
                "password_source": "keychain",
                "password_keychain_service": "zallet-rpc",
                "password_keychain_account": "localcheck",
                "password_keychain_present": True,
                "password_keychain_error": None,
                "probe_method": "getwalletinfo",
                "probe": {"status_code": 200, "http_ok": True, "rpc_error": None, "transport_error": None},
            },
            "wallet": {
                "summary_attempted": True,
                "summary_available": True,
                "account_count": 1,
                "accounts": [
                    {
                        "account_uuid": "uuid-1",
                        "name": "main",
                        "known_address_count": 40,
                        "spendable_balance_zec": "0.11271754",
                        "recent_transactions": [
                            {
                                "block_datetime": "2026-03-19T20:00:10Z",
                                "direction": "received",
                                "absolute_balance_delta_zec": "0.00425000",
                                "account_balance_delta_zec": "0.00425000",
                            },
                            {
                                "block_datetime": "2026-03-22T14:14:06Z",
                                "direction": "sent",
                                "absolute_balance_delta_zec": "0.00110000",
                                "account_balance_delta_zec": "-0.00110000",
                            },
                        ],
                    }
                ],
                "note_counts": {"orchard": 19, "sapling": 0, "sprout": 0},
                "operation_ids": [],
                "method_errors": {},
            },
            "notes": [
                "getwalletinfo appears to be placeholder-only in this build; use z_getbalances, z_listaccounts, z_getnotescount, z_listoperationids, and z_listtransactions for real wallet status."
            ],
        }

        rendered = check_wallet_status.render_summary(
            status,
            check_wallet_status.resolve_output_timezone("America/New_York"),
        )

        self.assertIn("Wallet status looks healthy.", rendered)
        self.assertIn("2026-03-22 04:53:37 PM EDT", rendered)
        self.assertIn("- 2026-03-19 04:00:10 PM EDT: main received 0.00425000 ZEC", rendered)
        self.assertIn("- 2026-03-22 10:14:06 AM EDT: main sent 0.00110000 ZEC", rendered)


class SendPreflightTests(unittest.TestCase):
    def test_build_report_auto_discovers_datadir_and_infers_user(self) -> None:
        args = argparse.Namespace(
            datadir=None,
            config=None,
            http_url=None,
            http_user=None,
            http_password_env=None,
            http_password_keychain_service=None,
            http_password_keychain_account=None,
            timeout=5,
            minconf=1,
            source_identifier="main",
            recipients_json='[{"address":"u1recipient","amount":"0.001"}]',
            recipients_file=None,
            privacy_policy="FullPrivacy",
            format="json",
        )

        with mock.patch.object(
            send_preflight,
            "discover_live_wallet_process",
            return_value={"datadir": "/Users/paul/dev/zallet/.zallet"},
        ), mock.patch.object(
            send_preflight,
            "load_toml_file",
            return_value={"rpc": {"bind": "127.0.0.1:28232", "auth": [{"user": "localcheck", "pwhash": "abc"}]}}
        ), mock.patch.object(
            send_preflight,
            "resolve_http_password",
            return_value={
                "source": None,
                "password": None,
                "env_present": None,
                "keychain_service": None,
                "keychain_account": None,
                "keychain_password_present": None,
                "keychain_error": None,
            },
        ), mock.patch.object(
            send_preflight,
            "json_rpc_request",
        ) as mocked_rpc:
            def fake_json_rpc_request(url, method, params, timeout, user, password):
                self.assertEqual(url, "http://127.0.0.1:28232")
                self.assertEqual(user, "localcheck")
                self.assertIsNone(password)
                if method == "z_listaccounts":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": [
                            {
                                "account_uuid": "uuid-1",
                                "name": "main",
                                "addresses": [{"ua": "u1source", "diversifier_index": 1}],
                            }
                        ],
                    }
                if method == "z_getbalances":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": {
                            "accounts": [
                                {"account_uuid": "uuid-1", "total": {"spendable": {"valueZat": 200000}}}
                            ]
                        },
                    }
                if method == "z_listoperationids":
                    return {"transport_error": None, "rpc_error": None, "rpc_result": []}
                if method == "getwalletinfo":
                    return {"transport_error": None, "rpc_error": None, "rpc_result": {}}
                if method == "z_listunifiedreceivers":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": {"orchard": "addr"},
                    }
                raise AssertionError(f"Unexpected method {method}")

            mocked_rpc.side_effect = fake_json_rpc_request
            report = send_preflight.build_report(args)

        self.assertEqual(report["transport"]["http_user"], "localcheck")
        self.assertEqual(report["source"]["from_address"], "u1source")
        self.assertTrue(any("Auto-discovered live wallet datadir" in note for note in report["notes"]))
        self.assertTrue(any("Inferred sole RPC user" in note for note in report["notes"]))

    def test_build_report_auto_selects_sole_account_when_from_is_omitted(self) -> None:
        args = argparse.Namespace(
            datadir="/Users/paul/dev/zallet/.zallet",
            config=None,
            http_url=None,
            http_user=None,
            http_password_env=None,
            http_password_keychain_service=None,
            http_password_keychain_account=None,
            timeout=5,
            minconf=1,
            source_identifier=None,
            recipients_json='[{"address":"u1recipient","amount":"0.001"}]',
            recipients_file=None,
            privacy_policy="FullPrivacy",
            format="json",
        )

        with mock.patch.object(
            send_preflight,
            "load_toml_file",
            return_value={"rpc": {"bind": "127.0.0.1:28232", "auth": [{"user": "localcheck", "pwhash": "abc"}]}}
        ), mock.patch.object(
            send_preflight,
            "json_rpc_request",
        ) as mocked_rpc:
            def fake_json_rpc_request(url, method, params, timeout, user, password):
                self.assertEqual(user, "localcheck")
                if method == "z_listaccounts":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": [
                            {
                                "account_uuid": "uuid-1",
                                "name": "main",
                                "addresses": [{"ua": "u1source", "diversifier_index": 1}],
                            }
                        ],
                    }
                if method == "z_getbalances":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": {
                            "accounts": [
                                {"account_uuid": "uuid-1", "total": {"spendable": {"valueZat": 200000}}}
                            ]
                        },
                    }
                if method == "z_listoperationids":
                    return {"transport_error": None, "rpc_error": None, "rpc_result": []}
                if method == "getwalletinfo":
                    return {"transport_error": None, "rpc_error": None, "rpc_result": {}}
                if method == "z_listunifiedreceivers":
                    return {
                        "transport_error": None,
                        "rpc_error": None,
                        "rpc_result": {"orchard": "addr"},
                    }
                raise AssertionError(f"Unexpected method {method}")

            mocked_rpc.side_effect = fake_json_rpc_request
            report = send_preflight.build_report(args)

        self.assertEqual(report["source"]["resolution"], "auto_account")
        self.assertEqual(report["source"]["from_address"], "u1source")
        self.assertTrue(any("Auto-selected the sole account" in note for note in report["notes"]))

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
        source, notes = send_preflight.resolve_source(accounts, "main")
        self.assertEqual(source["account_uuid"], "uuid-1")
        self.assertEqual(source["from_address"], "u1example")
        self.assertEqual(source["resolution"], "account")
        self.assertEqual(notes, [])


if __name__ == "__main__":
    unittest.main()
