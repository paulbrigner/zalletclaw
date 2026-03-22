# Manual Secret Operations

Switch to guidance mode for any step that touches wallet secrets.

## Hard Rules

- Do not ask the user to paste a mnemonic, passphrase, password, private key, PEM payload, or
  decrypted secret into chat.
- Do not execute mnemonic generation, mnemonic import, mnemonic export decryption, or unlock
  operations on the user's behalf.
- Provide the exact command, explain the prompt, and wait for the user to confirm completion.
- Ask for redacted output only when it is strictly needed.

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

## Unlocking Warning

Avoid running `walletpassphrase` with a plaintext passphrase through Codex, whether via
`zallet rpc ...` or direct HTTP tooling. The Zallet docs warn that command-line unlock flows can
leak the passphrase into terminal history.

If a send requires an unlocked wallet:

- tell the user why the wallet needs to be unlocked
- ask the user to unlock it locally with a method they trust
- continue only after they confirm the wallet is unlocked

## What to Request Back

- Ask for a success/failure confirmation.
- Ask for non-secret identifiers such as account UUIDs, seed fingerprints, or operation IDs.
- Ask for redacted config snippets or redacted errors when troubleshooting.
