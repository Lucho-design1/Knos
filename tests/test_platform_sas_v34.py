"""SAS attestations read as inputs (knos.platform.sas). Accounts are built in the test in the program's own layouts
(synthetic issuer, synthetic lab); no network."""
from __future__ import annotations

from solders.keypair import Keypair
from solders.pubkey import Pubkey

from knos.platform import sas

LAYOUT, FIELDS = bytes([12, 12, 10]), ("lab", "standard", "accredited")


def _s(b: bytes) -> bytes:
    return len(b).to_bytes(4, "little") + b


def credential_bytes(authority: Pubkey, name: str, signers) -> bytes:
    return bytes([0]) + bytes(authority) + _s(name.encode()) + len(signers).to_bytes(4, "little") + b"".join(bytes(s) for s in signers)


def schema_bytes(credential: Pubkey, name: str) -> bytes:
    names = b"".join(_s(f.encode()) for f in FIELDS)
    return bytes([1]) + bytes(credential) + _s(name.encode()) + _s(b"synthetic test schema") + _s(LAYOUT) + _s(names) + b"\x00\x01"


def attestation_bytes(nonce: Pubkey, credential: Pubkey, schema: Pubkey, data: bytes, signer: Pubkey, expiry: int = 0) -> bytes:
    return bytes([2]) + bytes(nonce) + bytes(credential) + bytes(schema) + _s(data) + bytes(signer) + expiry.to_bytes(8, "little", signed=True) + bytes(32)


class Ledger:
    def __init__(self, accounts: dict, now: int = 1_800_000_000):
        self.accounts, self._now = accounts, now

    def infos(self, keys):
        return [self.accounts.get(k) for k in keys]

    def now(self):
        return self._now


def world(expiry: int = 0, signers_now=None, owner=sas.PROGRAM, data=None):
    issuer, lab = Keypair().pubkey(), Keypair().pubkey()
    cred = sas.credential_pda(issuer, "accreditor")
    schema = sas.schema_pda(cred, "lab-accredited")
    body = data if data is not None else sas.encode(LAYOUT, ["Synthetic Lab", "ISO/IEC 17025", True])
    att = sas.attestation_pda(cred, schema, lab)
    accounts = {cred: (sas.PROGRAM, credential_bytes(issuer, "accreditor", signers_now if signers_now is not None else [issuer])),
                schema: (sas.PROGRAM, schema_bytes(cred, "lab-accredited")),
                att: (owner, attestation_bytes(lab, cred, schema, body, issuer, expiry))}
    return Ledger(accounts), cred, schema, lab, issuer


def test_an_attestation_by_an_authorized_signer_is_accepted_with_its_fields():
    led, cred, schema, lab, issuer = world()
    v = sas.check(led, cred, schema, lab, expect={"accredited": True})
    assert v.ok and v.fields == {"lab": "Synthetic Lab", "standard": "ISO/IEC 17025", "accredited": True} and v.signer == str(issuer)


def test_every_way_an_attestation_fails_is_refused_in_words():
    led, cred, schema, lab, _ = world()
    assert not sas.check(led, cred, schema, Keypair().pubkey()).ok                          # no attestation for that subject
    assert "differs" in sas.check(led, cred, schema, lab, expect={"standard": "GLP"}).why   # not what the order asks for
    led2, cred2, schema2, lab2, _ = world(expiry=1_700_000_000)
    assert "expired" in sas.check(led2, cred2, schema2, lab2).why                           # past the cluster's clock
    led3, cred3, schema3, lab3, _ = world(signers_now=[Keypair().pubkey()])
    assert "no longer an authorized signer" in sas.check(led3, cred3, schema3, lab3).why    # the issuer removed the signer
    led4, cred4, schema4, lab4, _ = world(owner=Keypair().pubkey())
    assert "not owned" in sas.check(led4, cred4, schema4, lab4).why                        # a look-alike account
    led5, cred5, schema5, lab5, _ = world(data=b"\x01\x02")
    assert "does not fit the schema" in sas.check(led5, cred5, schema5, lab5).why
    led6, cred6, schema6, lab6, _ = world()
    other_cred = sas.credential_pda(Keypair().pubkey(), "accreditor")                       # an issuer the order does not trust
    assert not sas.check(led6, other_cred, schema6, lab6).ok


def test_the_accounts_round_trip_through_the_readers():
    issuer, a, b = Keypair().pubkey(), Keypair().pubkey(), Keypair().pubkey()
    c = sas.read_credential(credential_bytes(issuer, "x", [a, b]))
    assert c.authority == issuer and c.name == "x" and c.signers == (a, b)
    s = sas.read_schema(schema_bytes(a, "lab-accredited"))
    assert s.fields == FIELDS and s.layout == LAYOUT and s.version == 1 and not s.paused
    assert sas.decode(bytes([3, 8, 11]), ("n", "m", "c"), sas.encode(bytes([3, 8, 11]), [7, -2, "k"])) == {"n": 7, "m": -2, "c": "k"}


def test_the_test_issuer_builders_carry_the_idl_discriminators_and_pdas():
    payer, issuer, lab = Keypair().pubkey(), Keypair().pubkey(), Keypair().pubkey()
    cred = sas.credential_pda(issuer, "n")
    ix = sas.create_credential_ix(payer, issuer, "n", [issuer])
    assert bytes(ix.data)[0] == 0 and ix.accounts[1].pubkey == cred and ix.accounts[2].is_signer
    schema = sas.schema_pda(cred, "s")
    ix = sas.create_schema_ix(payer, issuer, cred, "s", "d", LAYOUT, list(FIELDS))
    assert bytes(ix.data)[0] == 1 and ix.accounts[3].pubkey == schema
    ix = sas.create_attestation_ix(payer, issuer, cred, schema, lab, b"x", 5)
    assert bytes(ix.data)[0] == 6 and bytes(ix.data)[1:33] == bytes(lab) and ix.accounts[4].pubkey == sas.attestation_pda(cred, schema, lab)
    assert str(sas.PROGRAM) == "22zoJMtdu4tQc2PzL74ZUT7FrwgB1Udec8DdW4yw4BdG"
