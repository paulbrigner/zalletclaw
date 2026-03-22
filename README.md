# Zallet Operator Skill

This repository contains a dual-compatible Codex/OpenClaw skill for operating a local Zallet
wallet through its CLI and JSON-RPC interfaces.

## What This Skill Enables

When this skill is installed, an agent can work more effectively against a local Zallet wallet by
using repo-grounded instructions instead of guessing at CLI or RPC behavior.

The skill is intended to enable:

- inspection of wallet state, including balances, accounts, addresses, transactions, and async
  operations
- troubleshooting of `zallet.toml`, datadir selection, RPC startup, and RPC authentication issues
- construction of correct `zallet` CLI and JSON-RPC calls, including JSON parameter quoting
- guarded `z_sendmany` flows with preflight checks and explicit confirmation before execution
- explanation of Zallet-specific concepts such as accounts, known addresses, and Unified Address
  behavior
- safe handoff of secret-sensitive steps back to the user when manual intervention is required

## Prerequisites

For the full live workflow, this skill assumes:

- Zallet is installed locally on the same machine as the agent
- a Zallet wallet already exists or can be initialized locally by the user
- Zallet is running locally when you want live inspection, transaction lookup, or send execution
- JSON-RPC is enabled and reachable through Zallet's configured `rpc.bind` address
- the user can provide RPC credentials locally without pasting secrets into chat
- `python3` is available for the bundled helper scripts

Additional notes:

- Some guidance-only tasks do not require a running wallet. For example, the skill can still
  explain commands, config structure, and manual secret-handling steps without talking to a live
  node.
- Read-only inspection and guarded send flows do require a running Zallet instance.
- If your Zallet build does not include the optional `zallet rpc` CLI subcommand, the skill is
  expected to use direct HTTP JSON-RPC instead.
- If the wallet is encrypted, the user still needs to unlock it locally before any spend that
  requires private key access.

## How the Skill Operates

The skill has three main operating modes:

- Direct execution mode
  The agent can run non-secret CLI and JSON-RPC inspection tasks directly, such as listing
  accounts, checking balances, polling async operations, and inspecting transactions.
- Guidance mode
  For secret-sensitive tasks, the agent does not execute commands on your behalf. Instead, it
  gives exact CLI guidance and waits for you to complete the step locally.
- Guarded send mode
  For sends, the agent is expected to build a preflight summary first, restate the exact send, and
  require explicit confirmation before submitting anything.

## Supported Capability Areas

In practical terms, the skill can help with:

- generating or explaining Zallet config and startup commands
- reviewing RPC bind/auth setup and diagnosing whether HTTP JSON-RPC is reachable
- listing wallet accounts, account UUIDs, seed fingerprints, and known addresses
- explaining why a wallet has many known addresses and how Zallet derives them
- validating or inspecting recipient and source addresses
- showing balances at both total-wallet and per-account levels
- listing recent transactions and polling async operation IDs
- preparing and executing `z_sendmany` requests after confirmation

## Safety Boundaries

The skill is intentionally conservative around secrets.

It is designed to avoid automating:

- mnemonic generation, import, or export
- wallet encryption initialization
- wallet unlock passphrase entry
- requests for you to paste seeds, passphrases, private keys, PEM payloads, or decrypted secret
  material into chat

For those tasks, the skill should switch to guidance mode and tell you exactly what to run
locally.

## Transport Expectations

The skill is built around Zallet's JSON-RPC surface.

- If your Zallet build includes the optional `zallet rpc` subcommand, the agent can use that.
- If it does not, the skill is expected to fall back to direct HTTP JSON-RPC against the wallet's
  configured `rpc.bind` address.
- In practice, this means the skill can still work even when the JSON-RPC server is enabled but
  the CLI RPC client feature was not compiled into the binary.

## Helper Scripts in This Repository

The skill includes small helper scripts to make agent behavior more deterministic:

- `skills/zallet-operator/scripts/build_rpc_command.py`
  Builds shell-safe JSON-RPC commands and can choose between CLI and HTTP transport.
- `skills/zallet-operator/scripts/check_wallet_status.py`
  Intended for checking local binary, config, and RPC readiness.
- `skills/zallet-operator/scripts/send_preflight.py`
  Intended for deterministic send summaries before execution.

## Example Prompts

Typical prompts that should activate this skill include:

- `Use $zallet_operator to show my total balance in ZEC.`
- `Use $zallet_operator to list my accounts and addresses.`
- `Use $zallet_operator to explain why this wallet has 40 known addresses.`
- `Use $zallet_operator to troubleshoot why my RPC calls are failing.`
- `Use $zallet_operator to prepare a send and stop for confirmation before execution.`

## Repository Layout

- `skills/zallet-operator/SKILL.md`
  The main skill instructions consumed by Codex/OpenClaw-style skill systems.
- `skills/zallet-operator/references/`
  Supplemental reference material loaded only when needed.
- `skills/zallet-operator/scripts/`
  Small deterministic helpers used by the skill.
- `AGENTS.md`
  Stable maintainer guidance for future Codex sessions working on this repository.

## Disclaimer

This codebase was generated and iterated with Codex GPT-5.4.

It has not been formally audited or professionally reviewed for security, correctness,
compliance, or production readiness.

If you plan to use this code in production:

- perform your own engineering review
- add comprehensive automated and manual testing
- validate payment, webhook, and registration edge cases
- review infrastructure, auth, and secret-handling decisions

Use at your own risk.

## License Options

All code in this workspace is licensed under either of:

- Apache License, Version 2.0 (see [LICENSE-APACHE](LICENSE-APACHE) or http://www.apache.org/licenses/LICENSE-2.0)
- MIT license (see [LICENSE-MIT](LICENSE-MIT) or http://opensource.org/licenses/MIT)

at your option.
