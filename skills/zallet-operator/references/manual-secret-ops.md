# Manual Secret Operations

Switch to guidance mode for any step that touches wallet secrets.

## Hard Rules

- Do not ask the user to paste a mnemonic, passphrase, password, private key, PEM payload, or
  decrypted secret into chat.
- Do not execute mnemonic generation, mnemonic import, mnemonic export decryption, or unlock
  operations on the user's behalf.
- Provide the exact command, explain the prompt, and wait for the user to confirm completion.
- Ask for redacted output only when it is strictly needed.
- Do not suggest storing a plaintext RPC password in a committed config file just to make
  `zallet rpc` auto-auth work.

## Safe Wallet Setup Pattern

Guide the user through this sequence:

1. Generate or review config with `zallet example-config`.
2. Run `zallet init-wallet-encryption` locally if wallet encryption is needed.
3. Run either `zallet generate-mnemonic` or `zallet import-mnemonic` locally.
4. Start the wallet with `zallet start`.
5. Create or inspect accounts through non-secret RPC methods such as `z_getnewaccount`.

## Commands to Hand Back to the User

Initialize wallet encryption:

```bash
zallet --datadir /absolute/path/to/datadir init-wallet-encryption
```

Generate a mnemonic:

```bash
zallet --datadir /absolute/path/to/datadir generate-mnemonic
```

Import a mnemonic:

```bash
zallet --datadir /absolute/path/to/datadir import-mnemonic
```

Export a mnemonic for one account UUID:

```bash
zallet --datadir /absolute/path/to/datadir export-mnemonic --armor ACCOUNT_UUID > mnemonic.age
```

Create an RPC auth entry while letting the user type the password locally:

```bash
zallet --datadir /absolute/path/to/datadir add-rpc-user USERNAME
```

## Local RPC Password Storage

After the user creates or rotates an RPC password with `add-rpc-user`, steer them toward a local
secret store instead of a plaintext `password = "..."` entry in `zallet.toml`.

Preferred on macOS: store the password in Keychain.

```bash
security add-generic-password \
  -s zallet-rpc \
  -a USERNAME \
  -w 'your-rpc-password' \
  -U
```

When the skill needs to use that password through the helper scripts, instruct the user to point
the helper at the Keychain service and account:

```bash
python3 skills/zallet-operator/scripts/check_wallet_status.py \
  --datadir /absolute/path/to/datadir \
  --http-user USERNAME \
  --http-password-keychain-service zallet-rpc \
  --http-password-keychain-account USERNAME
```

If Keychain is not available, a temporary environment variable is the fallback:

```bash
export ZALLET_RPC_PASSWORD='your-rpc-password'
python3 skills/zallet-operator/scripts/check_wallet_status.py \
  --datadir /absolute/path/to/datadir \
  --http-user USERNAME \
  --http-password-env ZALLET_RPC_PASSWORD
```

For a one-shot send preflight without exporting the variable into the full shell session:

```bash
ZALLET_RPC_PASSWORD='your-rpc-password' \
python3 skills/zallet-operator/scripts/send_preflight.py \
  --datadir /absolute/path/to/datadir \
  --http-user USERNAME \
  --http-password-env ZALLET_RPC_PASSWORD \
  --from main \
  --recipients-json '[{"address":"RECIPIENT_ADDRESS","amount":"0.001"}]'
```

Important reminders:

- `--http-password-env` takes the environment variable name, not the password value.
- `--http-password-keychain-account` defaults to `--http-user` when omitted.
- Keep the password out of chat, shell history snippets that will be shared, and committed files.

## Unlocking Warning

Avoid running `walletpassphrase` with a plaintext passphrase through Codex, whether via
`zallet rpc ...` or direct HTTP tooling. The Zallet docs warn that command-line unlock flows can
leak the passphrase into terminal history.

If a send requires an unlocked wallet:

- tell the user why the wallet needs to be unlocked
- ask the user to unlock it locally with a method they trust
- continue only after they confirm the wallet is unlocked

## RPC Password Hygiene

- If the user needs direct HTTP JSON-RPC, prefer macOS Keychain or another local secret store over
  editing `zallet.toml` to add a plaintext `password` field.
- If Keychain is not available, a temporary environment variable in their local shell is an
  acceptable fallback.
- If they only have `pwhash` in config, explain that this is expected and preferable for server
  verification.
- If they need the optional CLI RPC client, explain that it may require a plaintext `password`
  entry for config-based auto-auth, which is a convenience tradeoff rather than the preferred
  default.

## What to Request Back

- Ask for a success/failure confirmation.
- Ask for non-secret identifiers such as account UUIDs, seed fingerprints, or operation IDs.
- Ask for redacted config snippets or redacted errors when troubleshooting.
