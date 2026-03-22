---
name: zallet_operator
description: "Operate the local Zallet Zcash CLI wallet through its CLI and JSON-RPC interfaces. Use when the agent needs to explain or run `zallet` commands, generate or troubleshoot `zallet.toml`, start a wallet, add RPC auth, inspect accounts, addresses, balances, transactions, or async operations, hand mnemonic or other secret-sensitive wallet steps back to the user with exact CLI guidance, or prepare and execute guarded `z_sendmany` send flows with explicit preflight and confirmation."
metadata: {"openclaw":{"os":["darwin","linux"],"requires":{"bins":["python3"]}}}
---

# Zallet Operator

## Overview

Use this skill to work against the local Zallet checkout without improvising wallet behavior.
Ground every answer in the adjacent repository and choose between direct execution, guidance
mode, and guarded send mode based on the task.

Primary source of truth:

- a local Zallet checkout, preferably a sibling `../zallet` repo when present

## Workflow Decision Tree

- Use [references/account-model.md](references/account-model.md) when the user is asking
  conceptual wallet questions about accounts, addresses, diversifiers, change, or privacy.
- Use [references/manual-secret-ops.md](references/manual-secret-ops.md) when the task touches
  mnemonic material, wallet encryption secrets, RPC unlock passphrases, or any other sensitive
  wallet secret.
- Use [references/send-flows.md](references/send-flows.md) when the task sends funds or prepares
  a `z_sendmany` request.
- Use [references/cli.md](references/cli.md) for config, startup, datadir, and top-level command
  guidance.
- Use [references/rpc.md](references/rpc.md) for JSON-RPC discovery, quoting, inspection, and
  operation polling.

## Trigger Examples

Use this skill for prompts such as:

- `Show me how to generate a Zallet config for this datadir.`
- `Help me inspect balances and accounts in my local Zallet wallet.`
- `Why does this wallet show so many known addresses?`
- `Explain what this account UUID, seedfp, or diversifier index means.`
- `What kind of Zcash address is this?`
- `Explain why this zallet rpc call is failing.`
- `Build the right z_sendmany command for these recipients.`
- `I need to import or export a mnemonic from Zallet.`
- `Help me poll a pending Zallet operation ID.`

## Grounding Rules

- Read the local Zallet docs or source when method or command behavior is unclear.
- Prefer local repository state over memory because Zallet is alpha and may change.
- Check `zallet --help` before assuming the `rpc` CLI subcommand exists; some builds expose the
  JSON-RPC server without compiling the RPC client subcommand.
- Prefer `zallet rpc help <method>` or `zallet rpc rpc.discover` when you need the live RPC
  contract when the CLI RPC client exists.
- Prefer `rg` against the adjacent repo when you need to confirm a command name, flag, or method.

## Guidance Mode

- Switch to guidance mode for secret-sensitive tasks instead of executing them.
- Provide the exact `zallet` CLI command with placeholders.
- Tell the user what prompt or output to expect.
- Ask only for sanitized confirmation or redacted output.
- Do not ask the user to paste a mnemonic, passphrase, private key, PEM payload, or recovery
  material into chat.

## Direct Execution Mode

- Use CLI or JSON-RPC directly for non-secret setup and inspection tasks.
- Use the helper script at `scripts/build_rpc_command.py` when shell quoting for JSON-RPC
  parameters is error-prone or when you need to choose between the `rpc` CLI subcommand and
  direct HTTP transport.
- Use `scripts/check_wallet_status.py` when the user is confused about binary features, config
  paths, RPC reachability, or auth shape.
- Use `scripts/send_preflight.py` when you need a deterministic send summary before asking for
  confirmation.
- Use absolute datadir paths when passing `--datadir`.
- Remember that relative config paths are resolved under the datadir.

## Guarded Send Mode

- Preflight the network, source, recipients, amount, memo handling, balance, and wallet state.
- Restate the exact send summary before execution.
- Require explicit user confirmation before sending.
- Execute the send once.
- Poll the returned operation ID with `z_getoperationstatus` or `z_getoperationresult`.
- Verify post-send state with inspection RPCs instead of blindly retrying.

## Example Routing

- If the user asks what an account, address, or diversifier means, use
  [references/account-model.md](references/account-model.md) before answering.
- If the user asks to create or import wallet secret material, switch to guidance mode and use
  [references/manual-secret-ops.md](references/manual-secret-ops.md).
- If the user asks to inspect wallet state, use [references/rpc.md](references/rpc.md) and favor
  read-only RPC methods.
- If the user asks to send funds, use [references/send-flows.md](references/send-flows.md),
  construct the command, summarize it, and wait for explicit confirmation.

## Resources

- [references/account-model.md](references/account-model.md)
- [references/cli.md](references/cli.md)
- [references/rpc.md](references/rpc.md)
- [references/manual-secret-ops.md](references/manual-secret-ops.md)
- [references/send-flows.md](references/send-flows.md)
- `scripts/build_rpc_command.py`
- `scripts/check_wallet_status.py`
- `scripts/send_preflight.py`
