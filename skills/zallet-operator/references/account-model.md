# Zallet Account and Address Model

Use this reference when the user is asking what the wallet structure means, not just how to run a
command.

## Accounts vs Addresses

- A Zallet account is the spending authority and balance bucket.
- An address is one receiver derived from or associated with that account.
- Multiple addresses can belong to the same account and still spend from the same underlying
  account balance.

## Why One Account Can Have Many Addresses

- Zallet's `z_listaccounts` intentionally returns all addresses known to the wallet for that
  account, not just a single primary receive address.
- `z_getaddressforaccount` derives a new address when it is called without an explicit
  diversifier index.
- Reusing one address is bad for privacy, so address growth over time is expected.

## Unified Addresses and Diversifiers

- The default account address in modern Zallet flows is a Unified Address.
- A Unified Address can bundle Orchard, Sapling, and transparent receivers together.
- Each derived address is identified by a diversifier index.
- Different diversifier indices produce different receive addresses for the same account.
- Gaps in the displayed indices are normal because not every index is valid for every receiver
  combination.

## Address Categories the Wallet May Know

- Unified receive addresses derived from the account.
- Sapling-only addresses.
- Transparent external addresses.
- Transparent internal change addresses.
- Transparent ephemeral addresses used for specialized flows.
- Imported watch-only addresses or viewing-key-derived addresses.

Use `listaddresses` when the user needs the source/category breakdown. Use `z_listaccounts` when
the user needs account-centric inventory.

## Interpreting "Known Addresses"

- "Known addresses" means addresses the wallet can map back to that account.
- It does not mean every address has a separate balance.
- It does not mean there are dozens of separate secrets to back up if they all descend from one
  seed.
- It does mean the wallet has derived, imported, or observed enough address metadata to track
  those receivers.

## Typicality

- A fresh wallet or lightly used account may have only a few known addresses.
- A wallet that has been tested, integrated with scripts, or used with fresh-address workflows can
  easily have dozens.
- A high count alone is not evidence of compromise or fund duplication.
