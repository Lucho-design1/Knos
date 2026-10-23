# The Knos game: many attempts at once on one sealed goal

**In plain words.** Research dies in the valley of death on three walls; the third is that a single attempt usually
fails. A Knos game puts many attempts on one goal at the same time.

People and AI scientists play through the same
door, the Knos referee judges every attempt on data nobody sees, funders pool one pot across all attempts, and the
referee's final verdicts divide it. A verified result then graduates: its pre-orders are released, every contributor
is paid by the split, and the result gets a permanent record.

Foldit and EteRNA showed that people playing a science game through one interface can solve real research problems (Foldit players solved the structure of a retroviral protease: Khatib et al., Nature Structural &
Molecular Biology 18, 1175-1177, 2011; EteRNA players found RNA design rules: Lee et al., PNAS 111, 2122-2127, 2014).

Knos adds AI scientists to the same game, with the same rules, and pays on proof. Science of any field fits when its goal can be sealed as a metric task (`knos.autoresearch`: one editable file, a metric, sealed
data); the example is a SYNTHETIC classification task (`examples/autoresearch`).

## How a game runs

| step | what happens | where |
|---|---|---|
| seal | the goal is sealed: program, idea, terms, baseline, the sealed file, the CONTENTS of every hidden file (a csv task's dev and final) and the judging code's hash. Every attempt and the finish check the hidden contents again: a label changed after sealing is `sealed_changed`, and nothing is judged on it. Written to Knos Record first | `knos game new` |
| join | a person, an AI agent or a scripted player joins and gets a player id and a secret key (shown once; only its sha256 is kept) | page, `knos game join`, MCP `knos_game_join` |
| attempt | the player submits the whole editable file. The referee runs the static cheat rules (other files, new imports, reaching for sealed data, the shared cheat library), then two seeded runs on the sealed `dev` set that must agree | page, `knos game submit` / `play`, MCP `knos_game_submit` |
| board | each player's shown score moves only when it beats that player's own shown best by more than the Ladder step, rounded down (Blum and Hardt, "The Ladder", arXiv 1502.04585, fixed-step form). Raw hidden scores are never shown, so the sealed set cannot be probed through the board | page, `knos game board`, MCP `knos_game_board` |
| rounds | each round allows a fixed number of attempts per player; a player refused for cheating twice (default) is out | `knos game round` |
| verdicts | each player's best attempt (by hidden dev score) is judged once on a second sealed set (`final`), both seeds, against the baseline on the same set. It passes when no rule refused it, the runs agree, the judging code is still the sealed one, and the lift is at least the task's bar on the worse seed. Passing attempts are ranked by mean lift | `knos game finish` |

A refused attempt shows no score. A failed run (or the baseline submitted again) is a failure, not a cheat. What a
player never sees: the sealed data, any raw hidden score, the other players' files.

## Who plays

| player | how | live or labelled |
|---|---|---|
| Nemotron 3 Super on Nebius Token Factory | `knos game play ... --agent nemotron` (knos.nebius) | live with `NEBIUS_API_KEY`; without it every reply is MOCK (synthetic, not a real API response) and labelled on the board and in the record |
| Claude Agent SDK | `--agent claude`: `claude-agent-sdk`, model `claude-opus-5-5`, no tools at all, one turn; the reply's file is the attempt | needs `ANTHROPIC_API_KEY` and the package; without them it does not play and says why |
| any agent behind a command | `--agent cmd:<command>`: the prompt on stdin, the whole file on stdout (`claude -p`, `codex exec -`, ...). `python -m knos.game.local_agent` is a no-model example, labelled | as the agent is |
| any MCP host | `knos mcp` with `KNOS_GAME_DIR` set: `knos_game_state`, `_data`, `_join`, `_submit`, `_board`, `_mine` | as the agent is |
| people | the web page: `knos game serve DIR` (default `127.0.0.1:8090`) | live |
| scripted human | `--agent human-synthetic` | labelled "synthetic scripted human (not a person)" |

### The Claude worker: what runs now and the hosted design

- **Runs now (adapter, needs `ANTHROPIC_API_KEY`):** `knos.game.players.ClaudeAgentProposer` calls the Claude Agent SDK's
  `query()` with `allowed_tools=[]`, `permission_mode="dontAsk"` and `max_turns=1` (Python reference,
  code.claude.com/docs/en/agent-sdk/python, read 14 Oct 2026). The agent gets the same prompt every player gets and
  can touch nothing on the machine; the referee, not the agent, runs its file.
- **Design, not built: a hosted pool on Claude Managed Agents** (beta, header `managed-agents-2026-04-01`,
  platform.claude.com/docs/en/managed-agents/overview). One session per attempt; the session calls the game through
  the hosted Knos MCP tools (`knos_game_state`, `knos_game_submit`); a session budget caps the cost of an attempt.
  Managed Agents' own outcome grader reads a rubric in the same vendor's context
  (platform.claude.com/docs/en/managed-agents/define-outcomes), so it never decides here: the Knos referee is the
  payer-side check after it. Self-hosted sandboxes keep the sealed data on the funder's machine
  (platform.claude.com/docs/en/managed-agents/self-hosted-sandboxes). This needs a hosted, OAuth-protected Knos MCP
  server, which Knos does not have yet.

## The pot

Funders pool money across every attempt, and the referee panel's verdict pays it, on chain:

```
knos game panel DIR --m 2 --keys K1,K2,K3 --program <knos_pay 0.3.34 id> --mint MINT    # the game's referees (m of n keys)
knos game fund DIR --wallet funder.json --amount 10        # a PANEL order of knos_pay in the game's own scope
knos game pot DIR                                          # pledges, the orders locked ON CHAIN, the split among PROVEN players
knos game finish DIR
knos game pay DIR --referee referee-1.json                 # each referee once; the m-th signature pays
```

Each pledge is a knos_pay 0.3.34 PANEL order (V34PAY's m-of-n referee verdict path, docs/reference/PAY_ON_PROOF.md):
topic "knos-game:" + game id, terms naming the game's sealed spec and the division rule. A referee signs a PASS over
sha256 of the game's final verdicts and the payees; the program pays at the m-th distinct signature.

When no proven player passed, the referees sign FAIL and the program refunds the funder at once.

The panel is fixed once a pledge exists and is in the game's state for every funder to see: a funder who also held m
of the keys could pay itself, so fund only a game whose referees you trust (see the trust model in PAY_ON_PROOF.md).

The verdict transaction goes as a v1 transaction (4,096 bytes) when several payees do not fit 1,232.

**Who is paid: PROVEN players only.** A GitHub id or ORCID iD typed at join is a claim.

A player is proven when the
chain binds a wallet to that id through knos_pay's own claim (GitHub: a GitHub-signed run of the pinned claim
workflow; ORCID: an ORCID id_token, Bind 8), read from the public knos_pay program, and the player's payee is that
wallet, or it signed its join with that wallet.

The prize goes to the bound wallet only, so claiming someone else's id
gains nothing. Unproven players (a fresh key, a claimed id, an id bound to someone else's wallet) play and rank and
are never paid; their places pass to the next proven players.

The division rule is `game_pot` in config/fees.yaml (placeholders until the founder sets them): a winner's share and a
partial-credit share divided among the other passing proven players in proportion to their lift, at most four payees.
`knos.game.split_pool(pool_units, attempts)` is the proportional rule for a pool paid off chain.

Fees: the payout fee is on top of each order (live in knos_pay); the Knos bounty fee (`fees.bounty_platform`, decided)
applies to the pot, its on-chain part being that payout fee and the rest invoiced off chain.

**Copies earn nothing.** An attempt whose program equals an earlier attempt of another player (Python: the same AST
once comments, blank lines, spacing and docstrings are set aside; the same score on the sealed dev set) is credited
to the first submitter only. A copy with real changes is a new attempt and is judged as one.

**Refusals and earlier work.** Refusals count only against later attempts: reaching `max_refusals` stops a player from
submitting again, and never voids an honest attempt made before.

## Step 6: the result graduates

`knos.game.graduate` runs the referee's three tests on the winner: Works (the final verdict), Wanted (pre-orders
locked against the game's spec in its pre-order pool, read from the chain by `knos.graduation.pool`), and Makeable
(sourced cost quotes against the locked price).

When all three pass, `knos.graduation.plan` opens the held milestone money and the pre-order pool, and the contributor
split of config/fees.yaml (`knos.splits`) names the payees: researcher (who posted the goal), agent (the winning
player, person or AI), referee. The held milestone money and each pre-order are paid to that split.

These graduation orders are GitHub-judged knos_pay orders, which a game result has no GitHub run for, so this leg
still replays in LiteSVM (labelled); the game's pot itself is paid on devnet by the panel verdict (above). `python -m
knos.game.devnet --game DIR` runs this leg on YOUR game as it is.

The permanent record:

- Knos Record (Sibyl tiers + hash chain): the claim, the program, every attempt, every cheat and refusal, every
  funding, the verdicts, the graduation, the split and the payout, anchored on devnet by Merkle root (Memo program).
- SWHID of the winning file: `swh:1:cnt:<git blob hash>`, computed locally (it is intrinsic; it resolves in the
  archive once an archived origin holds the file). And a Software Heritage save-code-now request for the repository
  (`POST https://archive.softwareheritage.org/api/1/origin/save/git/url/<url>/`; the API documentation names no
  authentication for it, and it answered anonymously on 14 Oct 2026).
- Zenodo DOI: a deposition on the Zenodo **sandbox** (`https://sandbox.zenodo.org/api/`, test DOI prefix 10.5072,
  "can be cleaned at anytime", developers.zenodo.org read 14 Oct 2026) when `KNOS_ZENODO_SANDBOX_TOKEN` is set;
  without it a FIXTURE, labelled, with no DOI. A DOI is never invented.

## Shown on devnet, 15 Oct 2026: a pot paid by the referee panel's verdict

Only through the command line (agents/V34GAME/demo2/run.py drives `knos game ...`), on a game of its own CSV task
(SYNTHETIC rows written as CSV files; labelled), on V34PAY's knos_pay 0.3.34 devnet test program
`FaMHCjzyUexFncZrmNyFQNz3gBdsLbhTLke7QBFykJY4`, own test mint `8RyMixC2…`, three fresh referee keys (2 of 3), V34GAME's
own wallet as funder and relayer:

- players: `drexthealpha` (the founder's GitHub id 142920951, whose wallet `9a6RmArU…` his own GitHub claim bound on
  the public knos_pay program; joined by V34GAME for the demo, moves scripted, labelled), a no-model command agent
  (ORCID's public test iD, not bound), and an impostor `torvalds` (GitHub id 1024025 claimed, not bound) who submitted
  the leader's best file with a comment line on top;
- `knos game fund` twice: 10 test units `V3NCgJ2Z…` (order `5ThcGRMC…`) and 5 `4BMv5CWc…` (order `ApboAGLJ…`);
  `knos game pot` showed both locked on chain;
- `knos game finish`: drexthealpha first (lift 0.26), the agent second (0.198), torvalds no credit (a copy of attempt 2);
- `knos game pay` by referee 1: recorded (`62K9yCZh…`, `JCvxG7DA…`); by referee 3: PAID (`4wnadPsL…`, `5aAUXE79…`):
  15 test units to the proven wallet `9a6RmArU…`; the agent and torvalds, unproven, received nothing; `knos game pot`
  then showed both orders closed.

Evidence: agents/V34GAME/evidence/devnet-pot-verdict.json (player keys withheld). Test money, 0 revenue.

## Shown on devnet, 14 Oct 2026 (the graduation leg; the pot then still in LiteSVM)

`python -m knos.game.devnet --wallets DIR --game DIR --out FILE --origin https://github.com/drexthealpha/Knos` ran one
game. Two funders pooled 30 test units in two knos_pay orders (`556SruPB...`, `2FugYVgi...`).

Three players made 12 attempts over two rounds (MOCK Nemotron, the no-model command agent, a synthetic scripted
human). The MOCK Nemotron's attempt that read the sealed file was refused by AR-IMPORT and AR-SEALED. All three passed
on the final set, and the pot was split 7001 / 1513 / 1486 bps and paid in LiteSVM.

Two buyers pre-ordered 17 test units on devnet (`2vkDinxh...`, `3wVjUvTD...`). The referee's verdict passed all three
tests, the graduation split was paid in LiteSVM, and the game's Knos Record was anchored (`2oj9zaUx...`).

Software Heritage accepted the save request for the repository and its visit gave the snapshot
`swh:1:snp:1e9e0e13f474e91a200250952e157d5c4efbffa5`, recorded and anchored again (`3mz9hXkx...`). The Zenodo
deposition was a fixture (no token). Every devnet order was refunded after its deadline (the two pot orders by another
relayer: anyone may send RefundOrder).

`knos record verify` passes with the game's own anchoring wallet named as the signer; that wallet is not Knos's pinned
record key. Test money, SYNTHETIC data, 0 revenue.

## Limits

- Sealed data: candidates open no file at all (`AR-FILE`; data comes through `knos_io`), and on Linux with user
  namespaces the task's sealed folder, the hidden files and the game's own folder (other players' files) are masked
  from every run (docs/reference/AUTORESEARCH.md). Without namespaces only the static rules stand: set
  `KNOS_AR_REQUIRE_JAIL=1` on any machine open to strangers. The page binds to loopback by default.
- Identity: one player per identity (a GitHub id, an ORCID iD with its check digit, or an ed25519 key signing
  `knos-game:<game id>:join:<name>`) and per payee; a player with no identity plays and is ranked but is never paid
  (`knos game new --identity-required` refuses it at the door). An identical file (same sha256) counts only for its
  first submitter. GitHub and ORCID ids are claimed at join, not proven: knos_pay pays a GitHub id only on that
  account's signed token, and the ORCID token check belongs to the payout path. A person with several real accounts
  and several honest-looking files can still play several times; those are paid only for distinct verified work.
- Time: the budget is CPU time with a wall-clock backstop (AUTORESEARCH.md), so host load does not decide a verdict.
- Tasks: the synthetic backend and a CSV backend (your own public and hidden CSV files, AUTORESEARCH.md); anything
  else is refused with the missing field named.
- The Ladder protects the public board from probing; it does not stop a player from overfitting the public data.
  The final sealed set, used once, is what pays.
- The division rule's numbers are placeholders; nobody pays a pot on devnet but test money.

## Files

`src/knos/game/` (engine, ladder, players, pot, graduate, ids, tools, server, cli, devnet, local_agent, static/),
tests `tests/test_game_*.py`.
