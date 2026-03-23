# Zallet RPC Reference

Use either `zallet rpc` or direct HTTP JSON-RPC for wallet inspection and async operation
management once a wallet is running.

## Transport Selection

- Discover a live wallet process before assuming default paths:
  - inspect `ps` output for `zallet ... start`
  - capture `--datadir` or `-d`
  - use `lsof -a -p <pid> -d cwd,txt -Fn` when available and permitted and when you need both the
    checkout path and the actual binary path
  - if `lsof` is unavailable or blocked, fall back to `ps` arguments plus targeted filesystem
    discovery near likely local checkouts such as `~/dev`, `~/src`, sibling `../zallet`, or any
    discovered datadir path instead of stopping early
- when a live process exists, prefer the resolved binary path from that process over a sibling
  checkout path or any other inferred source path
- do not anchor on a guessed sync-folder checkout such as iCloud Drive when a live process or
  discovered datadir points elsewhere
- Run `zallet --help` before assuming the `rpc` subcommand exists.
- Use `zallet rpc ...` when the binary exposes the `rpc` subcommand.
- Use direct HTTP JSON-RPC against the configured `rpc.bind` address when the binary does not.
- Use `scripts/check_wallet_status.py` when you need a deterministic check of binary features,
  config paths, auth shape, live HTTP reachability, log sync state, balances, note counts,
  pending operations, and recent transactions.
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

- Prefer macOS Keychain for local password storage when available.
- Use environment-backed credentials as a fallback when Keychain is not available or not desired.
- Do not inline plaintext RPC passwords into reusable scripts, committed files, or long-lived
  shell history.
- If the user needs to troubleshoot auth, ask for the username and redacted config shape, not the
  password itself.
- If the wallet only has `pwhash` auth entries, treat HTTP JSON-RPC with a local secret store or
  env-backed credentials as the primary transport.
- The helper scripts resolve passwords in this order: env var first, then Keychain.
- For wallet-status checks, if an initial unauthenticated probe returns `401 Unauthorized`, retry
  immediately with Keychain on macOS or an env-backed password before concluding the wallet is
  unreachable.

## Wallet Status Recipes

Use these default sequences for "what is the status of my wallet?" Start by checking for a live
wallet process instead of assuming the wallet is already running.

### No live process found

If `ps` does not show `zallet ... start`, report that the wallet is not currently running instead
of guessing a default datadir or probing stale config paths.

- If the user wants startup help, switch to [cli.md](cli.md).
- If the user wants config troubleshooting for a specific datadir, inspect that datadir
  explicitly rather than assuming `~/.zallet`.
- Do not describe the wallet as unreachable until you have distinguished "not running" from
  "running but auth or transport failed."
- Do not treat a failed probe of one guessed checkout or one TCC-restricted path as sufficient
  evidence that the live wallet cannot be inspected.

### macOS Keychain-backed default

Find the live process, datadir, checkout path, and binary path:

```bash
ps aux | rg '[z]allet( |$)'
lsof -a -p PID -d cwd,txt -Fn
```

Run the status helper with the discovered binary and datadir. If the config has a single
`[[rpc.auth]]` user, the helper will infer it automatically:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc
```

If the first probe shows `401 Unauthorized`, keep the same command and let the helper resolve the
password from the `zallet-rpc` Keychain item for the inferred or explicit RPC user.

### Environment-backed fallback

When Keychain is not available, point the helper at an existing local env var that already stores
the RPC password:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-user USERNAME \
  --http-password-env ZALLET_RPC_PASSWORD
```

If auth is still unavailable after the env-backed retry, stop and ask only for sanitized
confirmation of where the password is stored or whether auth is configured. Do not ask for the
plaintext password.

### Agent-friendly JSON summary

When another agent or script will summarize wallet status, prefer JSON output from the helper
instead of the human-oriented text format:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc \
  --format json
```

Use the same `--format json` flag with `--http-user` and `--http-password-env` for env-backed
auth. Summarize from the structured fields instead of scraping text output. When the helper
returns `summary_available = true`, that result is usually sufficient for the final wallet-status
answer without extra manual RPC calls.

### Direct human summary

When you want the helper to produce a user-facing wallet-status answer directly, prefer:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc \
  --format summary \
  --timezone local
```

Use `--timezone local` for the machine's local timezone, `--timezone utc` for explicit UTC, or an
IANA timezone such as `--timezone America/New_York` when you need a specific render target.

If the helper reports `summary_available = true`, stop there by default.

- Do not make extra RPC calls just to reconfirm balances, accounts, notes, operations, or recent
  transactions.
- Do not reopen `zallet.toml` separately when `client_user_inferred = true`; the helper has
  already selected the sole `[[rpc.auth]]` user.
- Do not inspect `zallet.log` separately when `log.latest_chain_tip` and
  `log.latest_reached_chain_tip_log_time` are present.
- Do not inspect the helper source just to confirm what the wallet-status path already gathers;
  the helper is the intended aggregator for these fields.
- Only do extra config, log, or RPC inspection when the helper is missing required fields or the
  result appears internally inconsistent.

## Common Success Interpretation

Use these quick interpretations when the helper succeeds:

- `supports_rpc_cli = false` means the wallet should be inspected over direct HTTP JSON-RPC; it is
  not itself a wallet failure.
- `client_user_inferred = true` means the helper selected the sole `[[rpc.auth]]` user from the
  config, so the operator does not need to guess a username or reopen the config unless debugging
  auth.
- `password_source = "keychain"` or an env-backed password source means auth resolution worked as
  intended; do not ask the user for the plaintext password.
- `summary_available = true` means the helper already gathered balance, account, note, operation,
  transaction, and sync-summary inputs for the final answer.
- Placeholder-heavy `getwalletinfo` fields such as `mnemonic_seedfp = "TODO"` or zeroed balances
  are expected in current alpha builds; use them only as a reachability signal.
- `recent_transactions` are ordered oldest-to-newest within the returned slice unless you
  explicitly reverse them before presenting them.
- Helper and log timestamps are commonly UTC; either convert them to the user's local timezone
  before presenting them or let the helper do it directly with `--format summary --timezone ...`.

## Helper JSON To Answer Map

When `summary_available = true`, build the wallet-status answer directly from these fields:

- `binary.resolved_path` plus the live process check: report the running binary path.
- `config.path` and `config.rpc_binds`: report the config path and exposed RPC bind.
- `binary.supports_rpc_cli`: choose between `zallet rpc` and direct HTTP JSON-RPC in the transport
  line.
- `http.client_user`, `http.client_user_inferred`, and `http.password_source`: explain how auth
  was resolved without asking for plaintext secrets.
- `log.latest_chain_tip.height`, `log.latest_chain_tip.log_time`, and
  `log.latest_reached_chain_tip_log_time`: report the sync signal and latest observed height.
- `wallet.accounts[*].recent_transactions[*].block_datetime`: convert recent activity timestamps
  to the user's local timezone before presenting them.
- `wallet.account_count` and `wallet.accounts[*].spendable_balance_zec`: report spendable balance
  and account inventory.
- `wallet.accounts[*].known_address_count`: report known address counts when relevant.
- `wallet.note_counts`: report note counts by pool.
- `wallet.operation_ids`: report pending async operations or explicitly say there are none.
- `wallet.accounts[*].recent_transactions`: report recent activity, noting that the helper returns
  each slice oldest-to-newest.
- `http.probe.rpc_result`: treat `getwalletinfo` as a reachability signal only when it is
  placeholder-heavy.

For direct helper-rendered summaries, `--format summary` already applies this mapping and can
render localized timestamps with `--timezone`.

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

## Compact Wallet Status Template

A good wallet-status answer should cover:

- live process and resolved binary path
- datadir, config path, and transport used
- sync signal from `zallet.log`, with timestamps rendered in the user's local timezone
- spendable balance, account inventory, note counts, and pending async operations
- recent transaction activity in local time
- alpha caveat when `getwalletinfo` is placeholder-heavy

Prefer a short paragraph or short flat list over a long narrative. Canonical compact phrasing:

```text
Wallet status looks healthy.

A live process is running from /path/to/zallet against datadir /path/to/datadir. JSON-RPC on
HOST:PORT was checked over TRANSPORT as USERNAME via AUTH_SOURCE.

Sync looks current: latest observed tip was HEIGHT at LOCAL_TIME, and the wallet logged reaching
chain tip at LOCAL_TIME. Spendable balance is AMOUNT ZEC across N account(s), with NOTE_COUNTS
and no pending async operations.

Recent activity (local time, oldest to newest):
- LOCAL_TIME: received AMOUNT ZEC
- LOCAL_TIME: sent AMOUNT ZEC

Alpha caveat: `getwalletinfo` is still placeholder-heavy in this build, so balance and activity
were summarized from the helper's richer status fields instead.
```

`check_wallet_status.py --format summary --timezone local` can emit nearly this shape directly.

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

Equivalent Keychain-backed check on macOS:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-user "${RPC_USER}" \
  --http-password-keychain-service zallet-rpc
```

Equivalent Keychain-backed check with JSON output for machine consumption:

```bash
python3 scripts/check_wallet_status.py \
  --binary /path/to/zallet \
  --datadir /absolute/path/to/datadir \
  --http-password-keychain-service zallet-rpc \
  --format json
```
