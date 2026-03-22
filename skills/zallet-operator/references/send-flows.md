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

## Privacy Policy Shortcuts

- Use `"FullPrivacy"` by default.
- Use `"AllowRevealedAmounts"` only if cross-pool movement is acceptable.
- Use `"AllowRevealedRecipients"` only if transparent recipients are acceptable.
- Use `"AllowRevealedSenders"` only if transparent spenders are acceptable.
- Use `"AllowFullyTransparent"`, `"AllowLinkingAccountAddresses"`, or `"NoPrivacy"` only after
  the user explicitly accepts those leaks.

## Build the Command

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
    "FROM_ADDRESS",
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
  --http-password-env ZALLET_RPC_PASSWORD \
  --from "ACCOUNT_NAME_OR_UUID_OR_ADDRESS" \
  --recipients-json '[{"address":"RECIPIENT_ADDRESS","amount":"0.01000000"}]'
```

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

Example poll command:

```bash
zallet rpc z_getoperationstatus '["OPERATION_ID"]'
```

## Verify After Sending

- Inspect the final operation result.
- Use `z_viewtransaction`, `z_listtransactions`, or balance methods to confirm expected state.
- If `z_viewtransaction` fails in an alpha build, rely on the completed operation result and
  balance delta before retrying or resubmitting.
- Prefer inspection over retrying when anything is ambiguous.
