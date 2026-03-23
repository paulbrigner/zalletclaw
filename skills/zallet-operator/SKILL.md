---
name: zallet_operator
description: "Operate the local Zallet Zcash CLI wallet through its CLI and JSON-RPC interfaces. Use when the agent needs to explain or run `zallet` commands, generate or troubleshoot `zallet.toml`, start a wallet, add RPC auth, check whether a wallet is running, synced, funded, idle, or has recent activity, inspect accounts, addresses, balances, transactions, or async operations, hand mnemonic or other secret-sensitive wallet steps back to the user with exact CLI guidance, or prepare and execute guarded `z_sendmany` send flows with explicit preflight and confirmation."
---

# Zallet Operator

## Overview

Use this skill to work against the local Zallet checkout without improvising wallet behavior.
Ground every answer in the adjacent repository and choose between direct execution, guidance
mode, and guarded send mode based on the task.

Primary source of truth:

- a local Zallet checkout, preferably a sibling `../zallet` repo when present
- when a live `zallet start` process exists, the resolved binary path from that process overrides
  any guessed checkout path

## Workflow Decision Tree

- Use the wallet-status workflow below when the user asks whether their wallet is up, synced,
  funded, idle, or has recent activity. Use [references/rpc.md](references/rpc.md) for the auth
  retry order, helper output modes, JSON mapping, and compact answer template.
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
- `What is the status of my wallet?`
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
- Discover the live wallet process before assuming default paths:
  - inspect `ps` output for a running `zallet ... start`
  - capture the explicit `--datadir` or `-d` value when present
  - use `lsof -a -p <pid> -d cwd,txt -Fn` when available and permitted to recover the running
    checkout path and the actual binary path
  - if `lsof` is unavailable or blocked, fall back to `ps` arguments plus targeted filesystem
    discovery near likely local checkouts such as `~/dev`, `~/src`, sibling `../zallet`, or any
    discovered datadir path instead of stopping early
- when a live process exists, prefer its resolved binary path over a sibling `../zallet` checkout
  or any other inferred source path
- do not anchor on a guessed iCloud Drive, Desktop, or other sync-folder checkout when a live
  process or discovered datadir points elsewhere
- do not stop at the first macOS privacy or TCC barrier if other non-elevated discovery paths are
  still available; only ask the user to run a command or grant more access after exhausting the
  live-process, datadir, and local-filesystem fallbacks
- Check `zallet --help` before assuming the `rpc` CLI subcommand exists; some builds expose the
  JSON-RPC server without compiling the RPC client subcommand.
- Prefer `zallet rpc help <method>` or `zallet rpc rpc.discover` when you need the live RPC
  contract when the CLI RPC client exists.
- Prefer `rg` against the adjacent repo when you need to confirm a command name, flag, or method.
- Render reported timestamps in the user's local timezone when that context is available. If it is
  not, label UTC explicitly instead of implying local time.

## Wallet Status Workflow

When the user asks for wallet status, answer from multiple signals instead of relying on
`getwalletinfo` alone.

Do not treat a missing `.zallet` directory in the current workspace as evidence that the wallet is
missing, stopped, or uninitialized. A running `zallet -d .zallet start` process may have been
launched from a different current working directory, so first resolve the live process cwd and the
explicit datadir before making any claim about where the wallet lives.

Operator recipe:

1. Find a live `zallet ... start` process and resolve its binary path and datadir.
2. If the process metadata is incomplete, keep going: infer the datadir from explicit `-d` or
   `--datadir` flags, or search nearby local checkouts and datadirs before asking the user for
   help.
3. Prefer this status sequence in order: `ps` -> `lsof` for cwd/binary when available -> helper
   script with absolute `--binary` and `--datadir` -> summarize helper output.
4. Run `python3 scripts/check_wallet_status.py --format json` with the best discovered binary,
   datadir, and the appropriate auth source.
5. Treat `check_wallet_status.py` as the wallet-status aggregator. It already resolves config and
   auth shape and collects the log sync signal, balances, note counts, pending operation IDs, and
   recent transactions.
6. If the config has a single `[[rpc.auth]]` user, let the helper infer that username instead of
   opening `zallet.toml` separately unless auth debugging requires it.
7. If authenticated HTTP succeeds and `summary_available` is true, stop and summarize from the
   helper output using the compact template in [references/rpc.md](references/rpc.md), or let the
   helper render the answer directly with `--format summary --timezone local`. Do not inspect the
   helper source, make extra RPC calls, or reopen the config or log unless the helper result is
   missing fields or appears inconsistent.
8. Do not ask the user to run the helper themselves, and do not request elevated access, unless
   non-elevated discovery has failed and you can clearly explain the specific blocker.
9. If no live process exists, report that the wallet is not currently running. Switch to
   [references/cli.md](references/cli.md) only if the user wants startup or config
   troubleshooting.

Common running-wallet command:

```bash
ps aux | rg '[z]allet( |$).*start'
lsof -a -p PID -d cwd,txt -Fn
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc \
  --format json
```

Swap the auth flags for `--http-user USERNAME --http-password-env ENV_VAR_NAME` when Keychain is
not the active local secret store.

For a direct user-facing status answer from the helper, prefer:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc \
  --format summary \
  --timezone local
```

### Wallet Status Answer Shape

Use these examples as a hard guardrail for weaker models.

Bad answer pattern:

- `Your Zallet wallet process is running, but the .zallet directory is not in the current workspace.`
- `Want me to find where the process actually wrote its data?`

Why this is bad:

- it treats the current workspace as the wallet location without proving that the wallet was
  launched there
- it stops after process discovery instead of resolving cwd or datadir
- it turns a direct status request into a menu of follow-up tasks

Good answer pattern:

- `Your wallet is running.`
- `It is using datadir /absolute/path/to/datadir.`
- `Sync status: ...`
- `Balance: ...`
- `Pending operations: ...`
- `Recent activity: ...`

Required behavior for wallet-status prompts:

- do not stop at `ps`
- do not infer the datadir from the current workspace
- do not answer with a next-steps menu when the helper can produce status now
- resolve the live wallet context and summarize the actual status

## Guidance Mode

- Switch to guidance mode for secret-sensitive tasks instead of executing them.
- Provide the exact `zallet` CLI command with placeholders.
- Tell the user what prompt or output to expect.
- Ask only for sanitized confirmation or redacted output.
- Do not ask the user to paste a mnemonic, passphrase, private key, PEM payload, or recovery
  material into chat.

## Direct Execution Mode

- Use CLI or JSON-RPC directly for non-secret setup and inspection tasks.
- Invoke repo Python helpers with `python3 ...` instead of assuming executable permissions are set.
- Use the helper script at `scripts/build_rpc_command.py` when shell quoting for JSON-RPC
  parameters is error-prone or when you need to choose between the `rpc` CLI subcommand and
  direct HTTP transport.
- Treat `scripts/check_wallet_status.py` as the default wallet-status entry point. It already
  covers config discovery, auth resolution, log sync inspection, balances, note counts, pending
  operations, and recent transactions.
- Prefer `--format json` when another agent will summarize the result or branch on specific
  fields. Prefer `--format summary --timezone local` when you want the helper to emit a compact
  user-facing status answer directly.
- If the helper returns `summary_available = true`, summarize that output and stop unless you are
  debugging a mismatch or extending the helper itself. Only inspect config, logs, or extra RPC
  methods when required fields are missing or the result appears inconsistent.
- Use `scripts/send_preflight.py` when you need a deterministic send summary before asking for
  confirmation.
- Use absolute datadir paths when passing `--datadir`.
- Remember that relative config paths are resolved under the datadir.

## Guarded Send Mode

- Preflight the network, source, recipients, amount, memo handling, balance, and wallet state.
- Restate the exact send summary before execution.
- Require explicit user confirmation before sending.
- After confirmation, follow the send recipe in [references/send-flows.md](references/send-flows.md) exactly instead of improvising parameters.
- Use the preflight result to obtain the concrete `from_address`; do not pass an account name directly to `z_sendmany`.
- When building recipient JSON for `scripts/send_preflight.py`, use the field name `amount`, not `amount_zec`.
- Remember that `scripts/send_preflight.py` takes `--datadir` or `--config`, not `--binary`.
- For `z_sendmany`, omit the fee parameter or pass `null`; any other fee value is rejected by current alpha builds.
- Poll the returned operation ID with `z_getoperationstatus` or `z_getoperationresult`.
- Verify post-send state with inspection RPCs instead of blindly retrying.
- Do not narrate scratch debugging or failed intermediate attempts to the user. Present only the preflight summary, the confirmation request, and the validated execution/result updates.

## Resources

- [references/account-model.md](references/account-model.md)
- [references/cli.md](references/cli.md)
- [references/rpc.md](references/rpc.md)
- [references/manual-secret-ops.md](references/manual-secret-ops.md)
- [references/send-flows.md](references/send-flows.md)
- `scripts/build_rpc_command.py`
- `scripts/check_wallet_status.py`
- `scripts/send_preflight.py`
