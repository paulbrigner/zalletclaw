# Zallet RPC Reference

Use either `zallet rpc` or direct HTTP JSON-RPC for wallet inspection and async operation
management once a wallet is running.

## Transport Selection

- Run `zallet --help` before assuming the `rpc` subcommand exists.
- Use `zallet rpc ...` when the binary exposes the `rpc` subcommand.
- Use direct HTTP JSON-RPC against the configured `rpc.bind` address when the binary does not.
- Expect `401 Unauthorized` when the server requires Basic auth and no credentials are supplied.
- Remember that `zallet.toml` usually stores only a password hash, so the agent cannot recover
  the plaintext RPC password.

## Connection Preconditions

- Start Zallet first with `zallet start`.
- Ensure the config enables at least one `rpc.bind` address.
- Ensure auth is configured if the wallet expects it.
- Use `--timeout` on `zallet rpc` when a request may run longer than the default 900 seconds.

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
