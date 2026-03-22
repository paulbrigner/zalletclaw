# Zallet RPC Reference

Use either `zallet rpc` or direct HTTP JSON-RPC for wallet inspection and async operation
management once a wallet is running.

## Transport Selection

- Run `zallet --help` before assuming the `rpc` subcommand exists.
- Use `zallet rpc ...` when the binary exposes the `rpc` subcommand.
- Use direct HTTP JSON-RPC against the configured `rpc.bind` address when the binary does not.
- Use `scripts/check_wallet_status.py` when you need a deterministic check of binary features,
  config paths, auth shape, and live HTTP reachability.
- Expect `401 Unauthorized` when the server requires Basic auth and no credentials are supplied.
- Remember that `zallet.toml` usually stores only a password hash, so the agent cannot recover
  the plaintext RPC password.
- Remember that the optional CLI RPC client can only auto-auth from a plaintext `password`
  config entry; a `pwhash` entry is sufficient for the server but not for client auto-auth.

## Connection Preconditions

- Start Zallet first with `zallet start`.
- Ensure the config enables at least one `rpc.bind` address.
- Ensure auth is configured if the wallet expects it.
- Use `--timeout` on `zallet rpc` when a request may run longer than the default 900 seconds.

## Auth Handling

- Prefer environment-backed credentials for direct HTTP requests.
- Do not inline plaintext RPC passwords into reusable scripts, committed files, or long-lived
  shell history.
- If the user needs to troubleshoot auth, ask for the username and redacted config shape, not the
  password itself.
- If the wallet only has `pwhash` auth entries, treat HTTP JSON-RPC with env-backed credentials as
  the primary transport.

## Parameter Encoding Rule

Every positional RPC parameter passed through `zallet rpc`, and every value inside the JSON-RPC
`params` array for direct HTTP requests, must be valid JSON.

- Pass numbers as `42` or `0.01`.
- Pass booleans as `true` or `false`.
- Pass null as `null`.
- Pass strings as JSON strings, for example `'"Main"'`.
- Pass arrays or objects as complete JSON text, for example `'["a"]'` or `'{"k":"v"}'`.

Use `scripts/build_rpc_command.py` when quoting is awkward or when you need transport fallback.

## Discovery Methods

- Use `zallet rpc help` to list supported RPC methods.
- Use `zallet rpc help '"method_name"'` when you need method-specific help text.
- Use `zallet rpc rpc.discover` when you want the OpenRPC schema.

For direct HTTP transport, call the same method names through a JSON-RPC POST body.

## Inspection Methods

- Use `z_listaccounts` and `z_getaccount` for account inventory.
- Use `z_getaddressforaccount`, `listaddresses`, and `z_listunifiedreceivers` for address work.
- Use `validateaddress` for transparent-address validation.
- Use `z_getbalances`, `z_gettotalbalance`, `z_listunspent`, and `z_getnotescount` for wallet
  balance and spendability checks.
- Use `z_listtransactions`, `z_viewtransaction`, `getrawtransaction`, and `decoderawtransaction`
  for transaction inspection.
- Use `getwalletinfo` for general wallet state, but expect alpha-stage incompleteness.

## Async Operation Methods

- Use `z_listoperationids` to enumerate tracked async operations.
- Use `z_getoperationstatus` to inspect an operation without removing it from memory.
- Use `z_getoperationresult` to fetch the final result and remove finished operations.
- Prefer polling an existing operation over resubmitting a send.

## Alpha Sharp Edges

- Expect some inspection RPCs to be incomplete or buggy while Zallet is alpha.
- If `z_viewtransaction` fails after a completed send, fall back to the async operation result,
  `z_listtransactions`, and balance deltas before concluding the send failed.
- Treat `getwalletinfo` as a partial state signal; fields like `unlocked_until` can still be
  useful even when the rest of the payload is placeholder-heavy.

## Example Commands

List accounts including known addresses:

```bash
zallet rpc z_listaccounts true
```

Fetch transactions for one account:

```bash
zallet rpc z_listtransactions '"ACCOUNT_UUID"' null null 0 20
```

Check one async operation:

```bash
zallet rpc z_getoperationstatus '["OPERATION_ID"]'
```

Equivalent HTTP request with env-backed credentials:

```bash
curl -sS \
  -u "${RPC_USER}:${ZALLET_RPC_PASSWORD}" \
  -H 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"z_getoperationstatus","params":[["OPERATION_ID"]]}' \
  "${ZALLET_RPC_URL}"
```

Check local binary, config, and auth status:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-user "${RPC_USER}" \
  --http-password-env ZALLET_RPC_PASSWORD
```
