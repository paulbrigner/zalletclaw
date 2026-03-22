# Zallet Operator Skill Workspace

This repository contains a dual-compatible Codex/OpenClaw skill for operating a local Zallet
wallet through its CLI and JSON-RPC interfaces.

## Maintainer Scope

- Treat the skill under `skills/zallet-operator` as the product.
- Treat this repository as the development home for the skill, its references, and its helper
  script.
- Use a local Zallet checkout as the source of truth. Prefer a sibling `../zallet` checkout when
  present; otherwise locate the repo explicitly before relying on source paths.
- Prefer local docs and source over memory because Zallet is alpha and behavior may change.

## Stable Operating Model

The skill should route work into three classes.

### 1. Human-only secret flows

Do not execute or request secret material for:

- wallet creation when it reveals or depends on mnemonic material
- mnemonic generation, import, or export
- wallet encryption steps that prompt for sensitive secrets
- any action that would echo seeds, PEM payloads, passwords, or recovery material back into chat

For these tasks, switch to guidance mode:

- provide exact `zallet` CLI usage with placeholders
- explain expected prompts and safe handling
- ask the user to perform the step manually
- request only sanitized confirmation or redacted output

### 2. Agent-assisted setup and inspection

The skill should directly support:

- config generation and explanation
- startup guidance
- RPC user setup guidance
- CLI help and RPC help
- account, address, balance, transaction, and operation inspection
- config and datadir troubleshooting

### 3. Guarded send flows

Send flows are in scope, but they must be confirmation-gated.

Required workflow:

1. Preflight the network, source account, destination, amount, memo handling, wallet state, and balance.
2. Construct the exact command or RPC payload.
3. Restate the send summary in plain language.
4. Require explicit user confirmation before execution.
5. Execute once.
6. Poll and inspect operation status instead of blindly retrying.
7. Verify the post-send state.

## Transport Guidance

- Treat JSON-RPC as the primary API surface for the skill.
- Use `zallet rpc ...` only when the installed Zallet binary was compiled with the `rpc-cli`
  feature.
- Fall back to direct HTTP JSON-RPC against the configured `rpc.bind` address when the binary does
  not include the `rpc` subcommand.
- Do not require plaintext RPC passwords in committed files. Prefer env vars, prompts, or other
  non-committed local mechanisms for authentication.

## Repository Layout

The expected maintained files are:

- `README.md`
- `LICENSE-APACHE`
- `LICENSE-MIT`
- `skills/zallet-operator/SKILL.md`
- `skills/zallet-operator/agents/openai.yaml`
- `skills/zallet-operator/references/`
- `skills/zallet-operator/scripts/build_rpc_command.py`

## Commit Hygiene

- Do not commit passwords, mnemonics, private keys, PEM payloads, or wallet datadirs.
- Keep examples generic; do not hardcode local usernames, absolute `/Users/...` paths, or
  machine-specific RPC endpoints unless they are clearly placeholders.
- Keep `SKILL.md` lean and procedural; put detailed operational guidance in `references/`.
- Keep the helper script aligned with the real transport behavior supported by current Zallet
  builds.

## Reference Files Worth Re-reading

- `../zallet/README.md`
- `../zallet/book/src/cli/README.md`
- `../zallet/book/src/cli/rpc.md`
- `../zallet/zallet/src/cli.rs`
- `../zallet/zallet/src/components/json_rpc/methods.rs`
