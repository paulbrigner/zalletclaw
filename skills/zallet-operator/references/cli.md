# Zallet CLI Reference

Use a local Zallet checkout as the source of truth:

- Prefer a sibling `../zallet` checkout when present.
- Otherwise locate the repo explicitly before relying on source paths.

## Core Invocation

- Use `zallet [--datadir ABS_PATH] [--config PATH] <subcommand>`.
- Pass an absolute path to `--datadir`.
- Remember that a relative `--config` path is resolved under the datadir.
- Remember that the default datadir is `~/.zallet`.
- Use `zallet help` or `zallet <subcommand> --help` when you need the compiled command surface.

## High-Value Subcommands

- Use `zallet example-config` to inspect or generate a full `zallet.toml`.
- Use `zallet start` to start the wallet, sync, and expose JSON-RPC.
- Use `zallet add-rpc-user USERNAME` to generate an `[[rpc.auth]]` entry after a local password
  prompt.
- Use `zallet rpc ...` to call JSON-RPC methods from the shell when the binary was compiled with
  the RPC client feature.
- Treat `zallet repair truncate-wallet HEIGHT` as a last-resort repair action.

## Common Patterns

Generate an example config to stdout:

```bash
zallet example-config -o - \
  --this-is-alpha-code-and-you-will-need-to-recreate-the-example-later
```

Start the wallet with an explicit datadir:

```bash
zallet --datadir /absolute/path/to/datadir start
```

Generate an RPC auth entry without exposing the password in chat:

```bash
zallet --datadir /absolute/path/to/datadir add-rpc-user USERNAME
```

## Practical Rules

- Expect alpha-only confirmation flags on some setup commands.
- Let the user type passwords for interactive commands like `add-rpc-user`.
- Prefer guidance over execution when a command will prompt for secret material.
- Check `zallet --help` first; some builds serve JSON-RPC but omit the `rpc` subcommand.
- Confirm that the wallet is running before troubleshooting RPC connectivity.
- Check `rpc.bind` and `[[rpc.auth]]` in the config when the RPC server is not reachable.

## Nearby Docs

- `README.md`
- `book/src/cli/README.md`
- `book/src/cli/start.md`
- `book/src/cli/example-config.md`
- `book/src/cli/add-rpc-user.md`
