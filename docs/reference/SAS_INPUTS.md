# Attestations as inputs: pay when an issuer you trust has attested a fact

Knos writes its acceptance receipts as Solana Attestation Service attestations ([RECEIPT.md](RECEIPT.md)). This page is
the other direction: an attestation someone else signed is a condition Knos checks before it counts evidence or
releases money. An accreditation body attests that a lab is accredited; a core facility attests that a sample was run;
a reviewer panel attests a result. None of them needs GitHub or CI, only a key its credential authorizes.

`knos.platform.sas.check(ledger, credential, schema, subject, expect=...)` follows the service's own verification rules
([README, "Verifying an attestation from another program"](https://github.com/solana-foundation/solana-attestation-service),
read 14 Oct 2026):

1. the account is at `["attestation", credential, schema, subject]` under `22zoJMtdu4tQc2PzL74ZUT7FrwgB1Udec8DdW4yw4BdG`;
2. that program owns it and its discriminator is 2;
3. its credential and schema are the ones the order names ("the credential you pass is the issuer you trust");
4. its expiry is 0 or later than the cluster's clock (never the local one);
5. Knos's own stricter rule: its signer is still one of the credential's authorized signers.

A closed attestation has no account, which is how revocation shows. The data is decoded with the schema's layout and
compared with `expect`. Layouts come from `program/src/state/{credential,schema,attestation}.rs`.

## On devnet (14 Oct 2026, a synthetic test issuer of the build's own key)

- Credential `9TwiHfDULBwYidMLRazc5znK75FREK2m516L4JmGYqbp` and schema `H9MgrAFSX3c1R1hwBPbfKtMz4XmVTZTuUwtN4PgoxPDz`
  (lab, standard, accredited),
  [`Ju9E1sYd…`](https://explorer.solana.com/tx/Ju9E1sYdihwKAmoh1RDBxBztJpkxdLCQ8JquiWWoRa1p68nagA4TtVwTAgAh87TGMhQdj9hqgmww23yjVUCoqGh?cluster=devnet).
- Attestation `Cena75W2HEEWekVSNK3342mdepBDKCRvHUDWRwHWzPka` for a synthetic lab,
  [`RjbWqeJ2…`](https://explorer.solana.com/tx/RjbWqeJ2XASak37Soi57QBoUtSNJdtwUYPbJYW9VDstFbXg9DyJmVNzU8QPuWFwKXRnyHN2AyEczXbFfsuhzEbT?cluster=devnet).
- `check` accepted it with its fields, refused a subject with no attestation and refused a wrong field value.

What it is not: proof that the lab did good work. It is proof that the issuer the order trusts said so, on chain, with
a key it controls. Which issuers an order trusts is the funder's choice, written in its terms.

Tests: `tests/test_platform_sas_v34.py`.
