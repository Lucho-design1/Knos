"""SOLANA-COVERAGE.md: every Solana devnet capability the official sources list on 22 Oct 2026 -> USED (the file that
uses it, and where a person meets it on each of Knos's five interfaces) or N/A (the source's own reason).

Sources, read 22 Oct 2026: solana.com/docs/rpc/http (52 methods) and /docs/rpc/websocket (18), /docs/tokens/extensions
(the Token-2022 ExtensionType list), /docs/core/programs, /docs/payments (Solana Pay, x402, MPP, Pay.sh, PaymentButton),
/docs/tools/actions, solana.com/upgrades and solana.com/news (Sept-Oct 2026), and devnet itself (getVersion,
the Feature Gate accounts, getMultipleAccounts on every program id: scripts/devnet_facts in the release notes).

  python scripts/solana_coverage.py           write docs/reference/SOLANA-COVERAGE.md
  python scripts/solana_coverage.py --check   exit 1 when the file is not what this table and the code say (CI)

A USED row names `file::text`; --check fails when that file no longer contains that text, so a row cannot outlive its code.
RPC rows are found in the code itself (every file that sends the method), never written by hand.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "reference" / "SOLANA-COVERAGE.md"
DOCS = "https://solana.com/docs"

HTTP = """getAccountInfo getBalance getBlock getBlockCommitment getBlockHeight getBlockProduction getBlocks
getBlocksWithLimit getBlockTime getClusterNodes getEpochInfo getEpochSchedule getFeeForMessage getFirstAvailableBlock
getGenesisHash getHealth getHighestSnapshotSlot getIdentity getInflationGovernor getInflationRate getInflationReward
getLargestAccounts getLatestBlockhash getLeaderSchedule getMaxRetransmitSlot getMaxShredInsertSlot
getMinimumBalanceForRentExemption getMultipleAccounts getProgramAccounts getRecentPerformanceSamples
getRecentPrioritizationFees getSignaturesForAddress getSignatureStatuses getSlot getSlotLeader getSlotLeaders
getStakeMinimumDelegation getSupply getTokenAccountBalance getTokenAccountsByDelegate getTokenAccountsByOwner
getTokenLargestAccounts getTokenSupply getTransaction getTransactionCount getVersion getVoteAccounts isBlockhashValid
minimumLedgerSlot requestAirdrop sendTransaction simulateTransaction""".split()
WS = """accountSubscribe accountUnsubscribe blockSubscribe blockUnsubscribe logsSubscribe logsUnsubscribe programSubscribe
programUnsubscribe rootSubscribe rootUnsubscribe signatureSubscribe signatureUnsubscribe slotSubscribe
slotsUpdatesSubscribe slotsUpdatesUnsubscribe slotUnsubscribe voteSubscribe voteUnsubscribe""".split()
# where the code sends RPC methods, and what a person sees there
SURFACES = [("web/", "front door"), ("apps/wanted/knos_wanted/static/", "app"), ("apps/wanted/knos_wanted/", "API"), ("src/knos/", "CLI")]
SCAN = [ROOT / "web", ROOT / "apps" / "wanted" / "knos_wanted", ROOT / "src" / "knos"]
SEEN = {"web/netfacts.js": "#network: Network facts panel / finality clock", "web/buyer.js": "#buyer receipts", "web/app.js": "the site's wallet",
        "web/live.js": "#live feed", "web/first.js": "first-run receipt", "web/anyissue.js": "fund any issue (fee preview)", "web/version.js": "#version",
        "apps/wanted/knos_wanted/static/valley.js": "project page", "apps/wanted/knos_wanted/static/ux.js": "finality after a lock or release",
        "apps/wanted/knos_wanted/static/app.js": "wallet and faucet"}
# the public devnet RPC's own answer when a stream is not offered (measured 21 Oct 2026 over wss://api.devnet.solana.com)
NOT_OFFERED = {"blockSubscribe": "the docs: unstable, only on a node started with --rpc-pubsub-enable-block-subscription; devnet answered 'not offered' live",
               "voteSubscribe": "the docs: unstable, only on a node started with --rpc-pubsub-enable-vote-subscription; devnet answered -32601 Method not found live"}



def u(cap, group, code, source, app="—", front="—", mcp="—", api="—", cli="—"):
    return {"cap": cap, "group": group, "status": "USED", "code": code, "source": source,
            "app": app, "front": front, "mcp": mcp, "api": api, "cli": cli}


def na(cap, group, reason, source):
    return {"cap": cap, "group": group, "status": "N/A", "code": "", "source": source, "reason": reason}


EXT = f"{DOCS}/tokens/extensions"
T22 = "src/knos/platform/token22.py"
CHX = "apps/wanted/knos_wanted/chainx.py"
READ = dict(cli="`knos fund` refuses a bounty mint whose extensions would stop the payment program from paying it (token22.mint_risks)", mcp="local `knos mcp` token check (mcp_more.token)")
BADGE = dict(app="project page: the maker's track-record badge per verified milestone", api="`GET /api/track`, `GET /api/project`")
ROWS = [
    # ---- Token-2022: every ExtensionType of the source (spl-token-2022 ExtensionType, docs/tokens/extensions)
    na("Uninitialized (ExtensionType 0)", "Token-2022", "the source: the zero type that ends the TLV list, not an extension a mint turns on; token22.extensions stops at it", EXT),
    u("TransferFeeConfig", "Token-2022", f"{T22}::TransferFeeConfig", EXT, **READ),
    u("TransferFeeAmount", "Token-2022", f"{T22}::TransferFeeAmount", EXT, **READ),
    u("MintCloseAuthority", "Token-2022", f"{CHX}::MintCloseAuthority", EXT, **BADGE, cli=READ["cli"]),
    u("ConfidentialTransferMint", "Token-2022", f"{T22}::ConfidentialTransferMint", EXT, **READ),
    u("ConfidentialTransferAccount", "Token-2022", f"{T22}::ConfidentialTransferAccount", EXT, **READ),
    u("DefaultAccountState", "Token-2022", f"{CHX}::DefaultAccountState", EXT, app="a funder's pledge receipt is frozen by default (a receipt never moves)",
      api="`POST /api/project/fund`", cli=READ["cli"]),
    u("ImmutableOwner", "Token-2022", f"{CHX}::ImmutableOwner", EXT, **BADGE),
    u("MemoTransfer", "Token-2022", f"{CHX}::MemoTransfer", EXT, app="the project's receipt ledger takes a pledge only with its order's claim as a memo", api="`POST /api/project/fund`", cli=READ["cli"]),
    u("NonTransferable", "Token-2022", f"{CHX}::NonTransferable", EXT, **BADGE, cli=READ["cli"]),
    u("InterestBearingConfig", "Token-2022", f"{T22}::InterestBearingConfig", EXT, **READ),
    u("CpiGuard", "Token-2022", f"{CHX}::CpiGuard", EXT, app="the project's receipt ledger refuses transfers by another program (CPI)", api="`POST /api/project/fund`"),
    u("PermanentDelegate", "Token-2022", f"{CHX}::PermanentDelegate", EXT, app="a refunded pledge's receipt is burned by the relayer (permanent delegate)", api="`POST /api/project/fund`", cli=READ["cli"]),
    u("NonTransferableAccount", "Token-2022", f"{T22}::NonTransferableAccount", EXT, **READ),
    u("TransferHook", "Token-2022", "apps/wanted/knos_wanted/chainx.py::project_credits", EXT,
      app="project page: 'Project credits ... held only in the project's own account' (each lock's units, moved in through knos_hook)",
      api="`GET /api/project` (credits: mint, hook, rules)", cli=READ["cli"]),
    u("TransferHookAccount", "Token-2022", f"{T22}::TransferHookAccount", EXT, **READ),
    u("ConfidentialTransferFeeConfig", "Token-2022", f"{T22}::ConfidentialTransferFeeConfig", EXT, **READ),
    u("ConfidentialTransferFeeAmount", "Token-2022", f"{T22}::ConfidentialTransferFeeAmount", EXT, **READ),
    u("MetadataPointer", "Token-2022", f"{CHX}::MetadataPointer", EXT, **BADGE),
    u("TokenMetadata", "Token-2022", f"{CHX}::TokenMetadata", EXT, **BADGE),
    u("GroupPointer", "Token-2022", f"{CHX}::GroupPointer", EXT, app="a project's badges are one group", api="`GET /api/track`"),
    u("TokenGroup", "Token-2022", f"{CHX}::TokenGroup", EXT, app="a project's badges are one group", api="`GET /api/track`"),
    u("GroupMemberPointer", "Token-2022", f"{CHX}::GroupMemberPointer", EXT, **BADGE),
    u("TokenGroupMember", "Token-2022", f"{CHX}::TokenGroupMember", EXT, **BADGE),
    u("ConfidentialMintBurn", "Token-2022", f"{T22}::ConfidentialMintBurn", EXT, **READ),
    u("ScaledUiAmount", "Token-2022", f"{T22}::ScaledUiAmount", EXT, **READ),
    u("Pausable", "Token-2022", f"{T22}::Pausable", EXT, **READ),
    u("PausableAccount", "Token-2022", f"{T22}::PausableAccount", EXT, **READ),
    na("AccountPaddingTest / MintPaddingTest", "Token-2022", "the source: test-only types (padding used in the program's own tests), never set on a real mint", EXT),
    # ---- native and SPL programs (docs/core/programs; deployed on devnet: read live)
    u("System Program (create, transfer, create-with-seed, nonce)", "Programs", f"{CHX}::create_with_seed", f"{DOCS}/core/programs",
      app="every lock and release", api="`POST /api/project/fund`", cli="`knos` money commands (knos.chain)", mcp="`knos_project_*` tools"),
    u("Durable nonce (System)", "Programs", "src/knos/platform/nonce.py::advance_ix", f"{DOCS}/core/transactions", cli="package `knos.platform.nonce`: Squads approvals signed offline (knos.platform.squads)"),
    u("Compute Budget", "Programs", "src/knos/platform/priority.py::set_compute_unit_limit", f"{DOCS}/core/fees", cli="limit from simulateTransaction, price from getRecentPrioritizationFees",
      front="#network: priority fee"),
    u("Address Lookup Table", "Programs", f"{CHX}::alt_ix", f"{DOCS}/core/transactions", app="many-payee releases", api="release transactions"),
    u("Feature Gate", "Programs", "web/netfacts.js::active features (feature gate)", f"{DOCS}/core/programs", front="#network: active features 324 of 329 (live)"),
    u("Ed25519 precompile", "Programs", "src/knos/proof/issuers.py::Ed25519SigVerify", f"{DOCS}/core/programs", cli="referee verdicts verified on chain",
      api="`GET /api/attest/key`"),
    u("Secp256k1 precompile", "Programs", f"{CHX}::secp256k1_ix", f"{DOCS}/core/programs", app="EVM-signed lab evidence", api="`POST /api/evidence/evm`"),
    u("Secp256r1 precompile", "Programs", "src/knos/settle/v2/passkey.py::Secp256r1SigVerify", f"{DOCS}/core/programs", app="passkey wallets approve locks",
      api="`POST /api/project/fund` passkey=true"),
    u("ZK ElGamal Proof", "Programs", f"{CHX}::ZK_ELGAMAL", f"{DOCS}/core/programs", app="private pledge amount, proofs verified on devnet", api="`POST /api/project/private`"),
    u("BPF Upgradeable Loader", "Programs", "programs-hook/knos_hook/Cargo.toml::knos-hook", f"{DOCS}/core/programs", cli="every Knos program is deployed with it (programs-v2 under its multisig; the hook on its own, programs-hook/)"),
    na("Loader v4", "Programs", "the source: the newer loader; Knos's programs stay under the Upgradeable Loader, whose upgrade authority the Squads multisig holds", f"{DOCS}/core/programs"),
    na("BPF Loader (deprecated) / BPF Loader 2", "Programs", "the source: deprecated loaders for older programs; nothing new is deployed with them", f"{DOCS}/core/programs"),
    na("Stake / Vote / Config", "Programs", "the source: staking and validator voting; Knos is not a validator or a staking product", f"{DOCS}/core/programs"),
    u("SPL Token", "Programs", "web/netfacts.js::TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", f"{DOCS}/tokens", app="test units held until the proof passes", front="#network: Knos test units",
      api="`POST /api/project/fund`", cli="`knos fund`"),
    u("Token-2022", "Programs", f"{CHX}::TOKEN22", f"{DOCS}/tokens", **BADGE),
    u("Associated Token Account", "Programs", f"{CHX}::ATA", f"{DOCS}/tokens", app="every payee's account", api="every funding transaction"),
    u("Memo", "Programs", f"{CHX}::knos release", f"{DOCS}/core/programs", app="each release's memo (brief and criteria hashes) on the receipt", api="`GET /api/project`"),
    u("Account Compression + Noop", "Programs", f"{CHX}::COMPRESSION", "https://spl.solana.com/account-compression", app="compressed track-record log", api="`GET /api/track`"),
    u("Name Service (.sol)", "Programs", f"{CHX}::sns_owner", "https://spl.solana.com/name-service", app="a project's .sol name", api="`GET /api/sns`"),
    u("Pyth push oracle", "Programs", f"{CHX}::PYTH_PUSH", "https://docs.pyth.network", app="a milestone stated in another currency", api="`GET /api/price`"),
    u("Squads v4", "Programs", "src/knos/platform/squads.py::SQDS4ep65", "https://docs.squads.so", app="company multisig", api="`POST /api/company/multisig`",
      cli="`knos boundary`: a Squads vault for an organisation's money"),
    u("Solana Attestation Service", "Programs", "src/knos/platform/sas.py::22zoJMtdu4tQc2PzL74ZUT7FrwgB1Udec8DdW4yw4BdG", "https://attest.solana.com",
      app="a wallet's verified milestones; the shareable Ready card (/ready/<criteria hash>); proven solvers first (/companies)",
      api="`GET /api/track`, `POST /api/ready/card`, `GET /api/solvers`"),
    na("Metaplex Token Metadata", "Programs", "the source (docs/tokens/extensions): Token-2022's TokenMetadata keeps a badge's metadata on the mint itself, no second program", EXT),
    na("Bubblegum (compressed NFTs)", "Programs", "the source: compressed NFTs; the track record is compressed with Account Compression directly and sells no NFT", "https://developers.metaplex.com/bubblegum"),
    na("Token Wrap", "Programs", "devnet: getAccountInfo on TwRapQCDhWkZRrDaHfZGuHxkZ91gHDRkyuzNqeU5MgR returned null on 22 Oct 2026 (not deployed)", "https://github.com/solana-program/token-wrap"),
    na("Stake Pool / Single-Validator Stake Pool", "Programs", "the source: pooled staking; Knos holds no stake", "https://spl.solana.com/stake-pool"),
    na("Token Swap", "Programs", "the source: an AMM; Knos does no speculation, and holding money needs no swap", "https://spl.solana.com/token-swap"),
    u("Record", "Programs", "apps/wanted/knos_wanted/chainstate.py::recr1L3PCGKLbckBqMNcJhuuyU1zgo8nBhfLVsJNwr5", "https://github.com/solana-program/record",
      app="a project, its trace and the pages it links survive a redeploy (read back from devnet)", api="`GET /api/project`, `GET /api/trace`"),
    # ---- payments (docs/payments) and Actions (docs/tools/actions)
    u("Solana Pay transaction request", "Payments", "apps/wanted/knos_wanted/blink.py::PAY_PATH", f"{DOCS}/payments/accept-payments",
      app="project page: 'Or from any wallet: Solana Pay' on every Ready milestone", api="`GET`/`POST /api/pay/fund` (OpenAPI)"),
    na("Solana Pay transfer request (plain SPL transfer link)", "Payments", "the source: a transfer request moves tokens to a wallet; a milestone's money must go through the payment program, so Knos answers a transaction request instead", f"{DOCS}/payments/accept-payments"),
    u("Solana Actions / Blinks", "Payments", "apps/wanted/knos_wanted/blink.py::/actions.json", f"{DOCS}/tools/actions", app="pre-order from a demand report with any wallet",
      api="`GET /actions.json`, `GET`/`POST /api/actions/preorder`", mcp="`knos_cross` returns the report the Blink sells"),
    u("x402 V2 (exact, self-facilitated)", "Payments", "apps/wanted/knos_wanted/x402.py::PAYMENT-SIGNATURE", f"{DOCS}/payments/agentic-payments/x402",
      api="`GET /api/x402/report` (402 + PAYMENT-REQUIRED)", cli="package `knos.labs.x402pay`: lab invoices paid over x402 V2"),
    u("x402 upto over Payment Channels", "Payments", "src/knos/money/x402_upto.py::payment-channels", f"{DOCS}/payments/agentic-payments/x402", cli="package `knos.money.x402_upto` (library; no command yet)"),
    na("MPP (Machine Payments Protocol)", "Payments", "the source: an HTTP-authentication alternative to x402 for the same 402 flow; Knos's paid route speaks x402 V2, which the source names for pay-per-request resources", f"{DOCS}/payments/agentic-payments"),
    na("Pay.sh", "Payments", "the source: a command-line gateway installed with Homebrew or npm in front of an HTTP API; Knos's server answers x402 itself (no gateway to install)", f"{DOCS}/payments/pay-sh"),
    na("PaymentButton", "Payments", "the source: drop-in React components; Knos's pages are plain JavaScript modules, no React", f"{DOCS}/payments/accept-payments"),
    u("Verify a payment landed", "Payments", "apps/wanted/knos_wanted/static/ux.js::signatureSubscribe", f"{DOCS}/payments/accept-payments", app="finality shown after every lock",
      api="`POST /api/project/confirm`"),
    # ---- upgrades (solana.com/upgrades) and changelog (solana.com/news, Sept-Oct 2026)
    u("Alpenglow finality (Agave 4.3)", "Upgrades", "src/knos/platform/finality.py::getAgGenesisCert", "https://solana.com/upgrades", app="measured lock-to-finalized seconds",
      front="#network finality clock", cli="knos.platform.finality"),
    u("v1 transactions, 4,096 bytes (SIMD-0385, Agave 4.2)", "Upgrades", "src/knos/chain.py::MAX_V1_BYTES", "https://solana.com/upgrades", cli="knos.chain sends v1 when a release outgrows 1,232 bytes",
      api="releases (valley ledger)"),
    u("Rent cut (Agave 4.2)", "Upgrades", "web/netfacts.js::getMinimumBalanceForRentExemption", "https://solana.com/upgrades", front="#network: rent for a token account, read live",
      app="rent returned on each release (chainx.rent_returned)"),
    u("200 ms slots", "Upgrades", "web/netfacts.js::slots per second", "https://solana.com/upgrades", front="#network: slots per second, measured"),
    na("sBPFv3 and deeper CPI nesting (Agave 4.4)", "Upgrades", "the source: 4.4 is on devnet as a beta (getVersion 4.4.0-beta.1); Knos's programs build for the default target until the feature is active everywhere", "https://solana.com/upgrades"),
    na("96 accounts per transaction (Agave 4.5)", "Upgrades", "the source: scheduled for 4.5, not yet on devnet", "https://solana.com/upgrades"),
    u("Durable-nonce deprecation (unscheduled)", "Upgrades", "src/knos/platform/blockhash.py::durable", "https://solana.com/upgrades", cli="recent-blockhash path kept beside the nonce path"),
    u("Payment Channels (1M payments/s, news Oct 2026)", "Changelog", "src/knos/money/x402_upto.py::payment_channels", "https://solana.com/news", cli="package `knos.money.x402_upto` (library; no command yet)"),
    na("SIMD-0675 geo-aware leader schedule", "Changelog", "the source: how validators are ordered; nothing an application sends changes", "https://solana.com/news"),
]


def files_with(method: str) -> list[str]:
    pat = re.compile(r"[\"'`]" + re.escape(method) + r"[\"'`]")
    tmpl = method.endswith("Unsubscribe")
    out = []
    for base in SCAN:
        for f in sorted(base.rglob("*")):
            if f.suffix not in (".js", ".py") or "build" in f.parts or "node_modules" in f.parts:
                continue
            t = f.read_text(encoding="utf-8", errors="replace")
            if pat.search(t) or (tmpl and "${k}Unsubscribe" in t and _subscribed(t, method)):
                out.append(f.relative_to(ROOT).as_posix())
    return out


def _subscribed(text: str, unsub: str) -> bool:
    """web/netfacts.js unsubscribes each stream it opened by kind (`${k}Unsubscribe`): the kind must be one it opens."""
    kind = unsub[: -len("Unsubscribe")]
    return f'"{kind}"' in text and f"{kind}Subscribe" in text


def rpc_rows() -> list[dict]:
    rows = []
    for m in HTTP + WS:
        group = "RPC HTTP" if m in HTTP else "RPC WebSocket"
        src = f"{DOCS}/rpc/{'http' if m in HTTP else 'websocket'}/{m.lower()}"
        fs = files_with(m)
        if not fs:
            rows.append(na(m, group, "not sent by any Knos code", src))
            continue
        where = {"app": [], "front": [], "api": [], "cli": []}
        for f in fs:
            key = next(k for p, k in SURFACES if f.startswith(p))
            col = {"front door": "front", "app": "app", "API": "api", "CLI": "cli"}[key]
            where[col].append(SEEN.get(f, f"`{Path(f).name}`"))
        note = NOT_OFFERED.get(m) or NOT_OFFERED.get(m.replace("Unsubscribe", "Subscribe"))
        lit = m if m in (ROOT / fs[0]).read_text(encoding="utf-8", errors="replace") else "${k}Unsubscribe"
        r = u(m, group, fs[0] + "::" + lit, src, **{k: "; ".join(dict.fromkeys(v)) or "—" for k, v in where.items()})
        if note:
            r["front"] = (r["front"] + "; asked, and shown as not offered: " + note)
        rows.append(r)
    return rows


def problems(rows: list[dict]) -> list[str]:
    bad = []
    for r in rows:
        if r["status"] != "USED":
            continue
        path, _, needle = r["code"].partition("::")
        f = ROOT / path
        if not f.exists() or needle not in f.read_text(encoding="utf-8", errors="replace"):
            bad.append(f"{r['cap']}: {path} does not contain {needle!r}")
    return bad


def render() -> str:
    rows = rpc_rows() + ROWS
    used = sum(r["status"] == "USED" for r in rows)
    out = ["# Solana devnet coverage", "",
           "Every capability the official Solana sources list on 22 Oct 2026, one row each: USED (the file that uses it and where a person",
           "meets it on each interface: the app at knos.onrender.com, the front door at drexthealpha.github.io/Knos, the hosted /mcp, the",
           "API and its OpenAPI document, and the `knos` CLI) or N/A with the source's own reason.", "",
           "Written by `scripts/solana_coverage.py`; `--check` fails CI when a row's file no longer holds its code. RPC rows are found in the code, not written by hand.", "",
           f"{len(rows)} rows: {used} USED, {len(rows) - used} N/A. Devnet on 22 Oct 2026: solana-core 4.4.0-beta.1, feature-set 3993424257,",
           "324 of 329 features active.", "",
           "| Capability | Group | Status | Code | App | Front door | /mcp | API | CLI | Source |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    esc = lambda s: str(s).replace("|", "\\|")  # noqa: E731
    for r in rows:
        if r["status"] == "USED":
            path, _, needle = r["code"].partition("::")
            out.append(f"| `{esc(r['cap'])}` | {r['group']} | USED | `{path}` | {esc(r['app'])} | {esc(r['front'])} | {esc(r['mcp'])} | {esc(r['api'])} | {esc(r['cli'])} | {r['source']} |")
        else:
            out.append(f"| `{esc(r['cap'])}` | {r['group']} | N/A | — | {esc(r['reason'])} | | | | | {r['source']} |")
    return "\n".join(out) + "\n"


def main(argv=None) -> int:
    check = "--check" in (argv if argv is not None else sys.argv[1:])
    bad = problems(rpc_rows() + ROWS)
    if bad:
        print("\n".join(bad), file=sys.stderr)
        return 1
    text = render()
    if check:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("SOLANA-COVERAGE.md matches the code" if ok else "SOLANA-COVERAGE.md differs: run python scripts/solana_coverage.py")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}: {text.count('| USED |')} USED, {text.count('| N/A |')} N/A")
    return 0


if __name__ == "__main__":
    sys.exit(main())
