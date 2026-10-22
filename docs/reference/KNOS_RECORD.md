<img src="../../web/brand/mark.svg" height="40" alt="Knos">

# Knos Record: a history whose edits show

**In plain words.** Every time Knos checks something (a research claim, an experiment, a verdict, a cheat it caught,
a refusal, a payout or a refund), it writes one line to a public file. Each line carries the fingerprint (hash) of the
line before it, so changing any old line breaks every line after it.

Every so often, one fingerprint for a whole batch
of lines (a Merkle root) is written into a Solana devnet transaction. Anyone can then recompute that fingerprint from
the file and compare it with the chain: `knos record verify`.

This page is about the journal in `src/knos/record/`. A supplier's public record page and its paid answer are a
different thing, described in [RECORD.md](RECORD.md).

## What a line is

One JSON object per line in `journal.jsonl`:

| field | meaning |
|---|---|
| `v` | format version, `1` |
| `seq` | the line's number, from 0 |
| `ts` | UTC time it was written |
| `kind` | `claim`, `paper`, or an event: `experiment`, `verification`, `verdict`, `cheat`, `refusal`, `payout`, `refund`, `funding`, `graduation`, `split`, `anchor` |
| `tier` | where Sibyl's memory engine keeps it: `WARM` (claim), `REFERENCE` (paper), `COLD` (every event) |
| `claim` | the claim or paper id the line is about, or null |
| `domain` | a short field name such as `ml`, or empty |
| `payload` | the facts: spec hash, pass or fail, cheat type, amount in the mint's smallest unit, devnet transaction signature |
| `prev` | the hash of the line before (`0` x 64 for the first) |
| `hash` | sha256 of the line's canonical JSON (sorted keys, no spaces) without `hash` |

The record is public, so a line is refused before anything is written when its payload looks like a secret. That
means a field named like a key, token, password or e-mail; a GitHub, Slack, AWS or API token; a PEM block; or a
signed token (JWT).

It also means an e-mail address; a home-folder path; an array of 32 or 64 bytes; or 64 bytes in base58 or hex under a
name that does not say it is a signature or a hash.

Demo data says `"synthetic": true` in its payload.

## Sibyl holds every line too

Knos remembers through Sibyl's memory engine and nothing else (`tests/test_sibyl_is_load_bearing.py`). The record
uses three of its tiers, in Sibyl's local store `sibyl.db` beside the file (tenant `knos-record`):

- **WARM**: one entity per research claim (category `record_claim`), holding its latest state.
- **COLD**: one journal event for every line, claims and papers included. This is the second witness.
- **REFERENCE**: one reference document per paper (`record:paper:<id>`).

A line goes to Sibyl first and to the file second. Without Sibyl's package there is no record at all.

Why it matters: cutting lines off the end of the file breaks no hash. Held to Sibyl's journal, the cut is caught;
with no memory, or with Sibyl's store deleted, it is not (`tests/test_record_verify.py`). An anchored root catches the
same cut once an anchor covers those lines.

## Anchoring a batch on Solana devnet

`knos record anchor [DIR] --keypair wallet.json` computes the Merkle root of every line since the last anchor (built
as Certificate Transparency builds one, RFC 9162 section 2.1), puts it in one transaction of Solana's SPL Memo program
(`MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr`), signed by the anchoring wallet, and appends an `anchor` line naming
the transaction:

```
knos-record:v1 root=<merkle root> first=<seq> last=<seq> head=<hash of line last>
```

No Knos program is used or changed. Devnet or a localnet only; mainnet is refused. Anchoring is never automatic: the
keeper of a record decides when. `--dry-run` shows the memo and sends nothing.

`knos record prove SEQ [DIR]` prints the audit path that shows one line is in its anchored batch, without the rest of
the file.

## Checking a record: `knos record verify [DIR | journal.jsonl]`

1. Every line parses, has exactly the fields above, sits at its `seq`, links to the line before, and hashes to what
   it says. Its tier matches its kind. Its payload passes the public-record check.
2. Each anchor covers the lines right after the previous one. The Merkle root recomputed from those lines is the root
   it states.
3. Each anchor's transaction is read from the cluster. It must exist, must have succeeded, must be signed by the
   wallet the line names, and its Memo instruction must be exactly the recomputed memo. `--offline` skips this, and
   the report says the chain was not read. A transaction that cannot be read is a failure, never a pass.
   Whether on chain or offline, the wallet that signed each anchor must be a trusted anchoring key. That key comes from
   outside the file: `--signer KEY` (repeat it), else `KNOS_RECORD_SIGNERS`, else the key pinned in
   `src/knos/record/anchoring.py`. Today the pinned key is the build's own devnet wallet
   `8aukezen9sAALWShcZKK3hi8WawBi4vR6qmLf764PGBv`. Without the pin, anyone could rewrite the whole file and anchor it
   again with a wallet of their own, and every hash and root would agree.
4. When Sibyl's store is beside the file, every line Sibyl's journal holds must be in the file, unchanged, and the
   other way round. Each claim entity and paper reference must point at its latest line. A public copy has no store
   beside it. It is checked by 1 to 3, and the report says Sibyl was not consulted.

Exit code 0 when every check passes, 1 otherwise. `--json` prints the report.

**Verifying your own record.** A record you anchored with your own wallet is not signed by Knos's pinned key, so a
plain `knos record verify` fails it on purpose (anyone could otherwise re-anchor a rewritten file). Name the key you
trust, which is the public key of the wallet that anchored it:

    knos record verify DIR --signer <your anchoring public key>
    KNOS_RECORD_SIGNERS=<key>[,<key>...] knos record verify DIR

The failure message names the anchor's signer and prints this flag with it. Trust that key only if it is yours, or
the key of someone you choose to believe.

`knos record anchor`, `journal` and `prove` need something after them (a folder, a seq or an option). On its own,
`knos record anchor` is still the record of the GitHub login `anchor`. `python -m knos.record anchor` needs no argument.

## The demo record (synthetic)

`src/knos/record/demo/journal.jsonl` is a synthetic record of ten lines: a paper, a claim, two experiments, a caught
cheat (`test_edited`), its refusal, a verdict, a payout line (synthetic: no transaction was sent for it), the claim's
new state, and an anchor. Its first nine lines are anchored on devnet:

| | |
|---|---|
| transaction | [`1C7bCGM7jHrj4XEkiWQKq3D4qYYj5mKxneGENJBjUoEEMzkQWHmRoaMMinkXePEpfS2A3E4vdWyfgEoB3m5qjFy`](https://explorer.solana.com/tx/1C7bCGM7jHrj4XEkiWQKq3D4qYYj5mKxneGENJBjUoEEMzkQWHmRoaMMinkXePEpfS2A3E4vdWyfgEoB3m5qjFy?cluster=devnet) |
| slot | 510678984 |
| Merkle root of seq 0..8 | `2817c4837adc981d73cd676c73930deb998cde88e07fb27ba088ec005e54b599` |
| signer (devnet wallet) | `8aukezen9sAALWShcZKK3hi8WawBi4vR6qmLf764PGBv` |

Check it yourself: `knos record verify src/knos/record/demo` (reads devnet), or `--offline` to recompute only.

## For code in Knos

```python
from knos import record
record.claim("claim-42", {"title": "...", "spec_hash": "..."}, domain="ml")
record.append("verdict", {"spec_hash": "...", "passed": False, "cheat": "test_edited"}, claim="claim-42")
record.paper("arxiv:2401.00001", {"title": "...", "sha256": "..."})
record.anchor(keypair="wallet.json")
record.verify()
```

Every part of Knos writes the record only through `append`, `claim` and `paper`. The default folder is
`$KNOS_RECORD_DIR`, else `~/.knos/record`.

## What this is not

The record does not stop edits. It makes them show, to someone who checks, within these limits:

- An anchor shows that a batch of lines existed in this order at the slot of its transaction. It does not show that
  what a line says is true. The referee and the checks that wrote the line are what vouch for that.
- Whoever holds a trusted anchoring key can rewrite the file and anchor the new version. The pin moves trust to that
  key; it does not remove it. Anyone can list every transaction the key signed, so two different anchored histories
  can both be seen. Today one key, the build's devnet wallet, anchors this record.
- A record with no anchor proves nothing about its past: a rewritten copy would verify the same way. The report says
  when there is no anchor.
- Lines written after the last anchor have only the file's hashes and Sibyl's journal behind them. Cutting them from
  the end of a public copy, which has no Sibyl store beside it, is not caught until the next anchor.
- Nobody outside Knos has reviewed this code.
