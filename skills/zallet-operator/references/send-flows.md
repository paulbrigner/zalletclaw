# Guarded Send Flows

Use this workflow for every send request.

## Preflight Checklist

- Confirm the target network and datadir.
- Confirm the source account or source address.
- Confirm each recipient address and amount.
- Confirm whether any memo is needed.
- Confirm the wallet is synced enough for the user's tolerance.
- Confirm the wallet has enough spendable balance for the request.
- Confirm the wallet is unlocked if spending requires private key access.
- Confirm the privacy policy the user accepts.

When possible, generate the preflight summary with `scripts/send_preflight.py` instead of doing
the entire checklist ad hoc in prose.

## Construction Rules

- Use `z_sendmany` for sends.
- Avoid `ANY_TADDR`; the current implementation rejects it.
- Pass recipient amounts as an array of JSON objects with `address`, `amount`, and optional
  `memo`.
- Pass `memo` only for shielded recipients.
- Pass decimal amounts with at most 8 digits of precision.
- Omit the `fee` parameter or pass `null`; any other value is rejected.
- Avoid duplicated recipient addresses in the same request.
- Resolve the final `from_address` before execution; do not pass an account name directly to
  `z_sendmany`.

## Privacy Policy Shortcuts

- Use `"FullPrivacy"` by default.
- Use `"AllowRevealedAmounts"` only if cross-pool movement is acceptable.
- Use `"AllowRevealedRecipients"` only if transparent recipients are acceptable.
- Use `"AllowRevealedSenders"` only if transparent spenders are acceptable.
- Use `"AllowFullyTransparent"`, `"AllowLinkingAccountAddresses"`, or `"NoPrivacy"` only after
  the user explicitly accepts those leaks.

## Build the Command

Prefer the helper script to assemble a shell-safe command.

Hard guardrails for smaller models:

- `scripts/send_preflight.py` does not accept `--binary`; use `--datadir` or `--config` plus auth flags.
- `--recipients-json` must be raw JSON text, not a path. Use `--recipients-file` when passing a file path.
- Recipient objects for the preflight helper must use `address`, `amount`, and optional `memo`.
- The `from` value in the preflight helper may be an account name, account UUID, or address, but the final `z_sendmany` call must use the resolved concrete `from_address`, not the original account name.
- Current alpha builds reject a non-null explicit fee. Use `null` for the fee slot or omit the fee entirely when the transport/method variant supports omission.
- Do not write one-off Python scratch scripts to discover the final RPC shape after confirmation. Use the documented command shape below or `scripts/build_rpc_command.py`.

Prefer the helper script to assemble a shell-safe command:

```bash
python3 scripts/build_rpc_command.py \
  --binary /path/to/zallet \
  --transport auto \
  --datadir /absolute/path/to/datadir \
  --http-url "${ZALLET_RPC_URL}" \
  --http-user "${RPC_USER}" \
  --http-password-env ZALLET_RPC_PASSWORD \
  --method z_sendmany \
  --params-json '[
    "RESOLVED_FROM_ADDRESS",
    [{"address":"RECIPIENT_ADDRESS","amount":0.01000000}],
    1,
    null,
    "FullPrivacy"
  ]'
```

If the binary has the `rpc` subcommand, the helper emits `zallet rpc ...`. Otherwise it emits a
direct `curl` JSON-RPC request against the configured RPC server. Inspect the emitted command
before execution.

Prefer the deterministic preflight helper before execution:

```bash
python3 scripts/send_preflight.py \
  --datadir /absolute/path/to/datadir \
  --http-user "${RPC_USER}" \
  --http-password-keychain-service zallet-rpc \
  --from "ACCOUNT_NAME_OR_UUID_OR_ADDRESS" \
  --recipients-json '[{"address":"RECIPIENT_ADDRESS","amount":"0.01000000"}]'
```

If you already have the preflight output, reuse its resolved `from_address` in the final send.
Do not rerun ad hoc discovery after the user confirms unless the wallet state changed.

Canonical final `z_sendmany` parameter shape:

```json
[
  "RESOLVED_FROM_ADDRESS",
  [{"address":"RECIPIENT_ADDRESS","amount":0.01000000}],
  1,
  null,
  "FullPrivacy"
]
```

If the live build rejects the 5-parameter form because it calculates fees internally, fall back to:

```json
[
  "RESOLVED_FROM_ADDRESS",
  [{"address":"RECIPIENT_ADDRESS","amount":0.01000000}],
  1
]
```

Do not switch the first parameter back to an account name during fallback.

## Require Explicit Confirmation

Restate the send in plain language before running it:

- source
- recipients
- total amount
- memo presence
- privacy policy
- datadir or config target

Run the send only after the user gives an explicit confirmation.

## Execute and Poll

- Run the send command once.
- Capture the returned operation ID.
- Poll with `z_getoperationstatus` while the operation is pending.
- Use `z_getoperationresult` once the operation is finished and you want the terminal result.
- If the first confirmed execution attempt fails because the method shape is alpha-specific,
  correct the parameter shape once and retry exactly once with the same recipient set and
  resolved `from_address`. Do not keep experimenting in a loop.

Bad execution pattern:

- tell the user about each failed scratch attempt
- pass the account name directly to `z_sendmany`
- discover after confirmation that the helper uses `amount` instead of `amount_zec`
- discover after confirmation that `--recipients-json` expects inline JSON instead of a file path
- discover after confirmation that the fee must be `null` or omitted

Good execution pattern:

- finish all shape validation during preflight
- restate one clean confirmation summary
- execute a documented `z_sendmany` shape using the resolved `from_address`
- report only the operation ID, final status, and resulting txid

Example poll command:

```bash
zallet rpc z_getoperationstatus '["OPERATION_ID"]'
```

Direct HTTP JSON-RPC example with the canonical 5-parameter send shape:

```bash
curl -sS \
  -u "${RPC_USER}:${ZALLET_RPC_PASSWORD}" \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"z_sendmany","params":["RESOLVED_FROM_ADDRESS",[{"address":"RECIPIENT_ADDRESS","amount":0.01000000}],1,null,"FullPrivacy"]}' \
  "${ZALLET_RPC_URL}"
```

Fallback direct HTTP JSON-RPC example when the live build rejects an explicit fee slot:

```bash
curl -sS \
  -u "${RPC_USER}:${ZALLET_RPC_PASSWORD}" \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"z_sendmany","params":["RESOLVED_FROM_ADDRESS",[{"address":"RECIPIENT_ADDRESS","amount":0.01000000}],1]}' \
  "${ZALLET_RPC_URL}"
```

## Verify After Sending

- Inspect the final operation result.
- Use `z_viewtransaction`, `z_listtransactions`, or balance methods to confirm expected state.
- If `z_viewtransaction` fails in an alpha build, rely on the completed operation result and
  balance delta before retrying or resubmitting.
- Prefer inspection over retrying when anything is ambiguous.
