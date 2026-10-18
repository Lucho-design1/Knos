//! knos-frost: the Zcash Foundation's FROST (frost-ed25519 3.0.0, RFC 9591 FROST(Ed25519, SHA-512)) as one JSON
//! command for Knos's referee hosts. `knos-frost <op>` reads one JSON object on stdin and writes one on stdout.
//! Secrets (DKG secret packages, key packages, nonces) come in and go out only through stdin/stdout, never argv.
//!
//! Participants are numbered 1..=n (Knos: 1 = the Render app server, 2 = GitHub Actions, 3 = the founder's PC).
//!
//!   dkg1      {id, max, min}                         -> {secret, package}                 DKG round 1 (no dealer)
//!   dkg2      {secret, packages: {j: round1 pkg}}    -> {secret, packages: {j: round2 pkg}}
//!   dkg3      {secret, round1: {j: ..}, round2: {j: ..}} -> {key_package, public, group_key}
//!   dealer    {max, min}                             -> {shares: {i: key_package}, public, group_key}   (tests only)
//!   commit    {key_package}                          -> {nonces, commitments}             signing round 1
//!   package   {commitments: {i: ..}, message: hex}   -> {signing_package}                 the coordinator
//!   sign      {key_package, nonces, signing_package, message: hex} -> {share}             signing round 2
//!   aggregate {signing_package, shares: {i: ..}, public} -> {signature, group_key}       verifies every share
//!   verify    {group_key: hex, message: hex, signature: hex} -> {ok}
//!   info      {public}                               -> {group_key, ids, min}
use std::collections::BTreeMap;
use std::io::Read;

use frost_ed25519 as frost;
use frost::keys::dkg;
use rand_core::OsRng;
use frost::Identifier;
use serde_json::{json, Map, Value};

type R<T> = Result<T, String>;

fn ident(i: u16) -> R<Identifier> {
    Identifier::try_from(i).map_err(|e| format!("identifier {i}: {e}"))
}

fn num(id: &Identifier, max: u16) -> R<u16> {
    for i in 1..=max.max(16) {
        if ident(i)? == *id {
            return Ok(i);
        }
    }
    Err("an identifier outside 1..n".into())
}

fn field<'a>(v: &'a Value, k: &str) -> R<&'a Value> {
    v.get(k).ok_or_else(|| format!("missing field {k}"))
}

fn of<T: serde::de::DeserializeOwned>(v: &Value, k: &str) -> R<T> {
    serde_json::from_value(field(v, k)?.clone()).map_err(|e| format!("{k}: {e}"))
}

fn to<T: serde::Serialize>(t: &T) -> R<Value> {
    serde_json::to_value(t).map_err(|e| e.to_string())
}

fn u16_of(v: &Value, k: &str) -> R<u16> {
    let n = field(v, k)?.as_u64().ok_or_else(|| format!("{k}: a number"))?;
    u16::try_from(n).map_err(|_| format!("{k}: 1..65535"))
}

fn map_of<T: serde::de::DeserializeOwned>(v: &Value, k: &str) -> R<BTreeMap<Identifier, T>> {
    let m = field(v, k)?.as_object().ok_or_else(|| format!("{k}: an object keyed by participant number"))?;
    let mut out = BTreeMap::new();
    for (i, x) in m {
        let n: u16 = i.parse().map_err(|_| format!("{k}: key {i} is not a participant number"))?;
        out.insert(ident(n)?, serde_json::from_value(x.clone()).map_err(|e| format!("{k}.{i}: {e}"))?);
    }
    Ok(out)
}

fn map_to<T: serde::Serialize>(m: &BTreeMap<Identifier, T>, max: u16) -> R<Value> {
    let mut out = Map::new();
    for (id, x) in m {
        out.insert(num(id, max)?.to_string(), to(x)?);
    }
    Ok(Value::Object(out))
}

fn hexb(v: &Value, k: &str) -> R<Vec<u8>> {
    hex::decode(field(v, k)?.as_str().ok_or_else(|| format!("{k}: hex"))?).map_err(|e| format!("{k}: {e}"))
}

fn group_key(public: &frost::keys::PublicKeyPackage) -> R<String> {
    Ok(hex::encode(public.verifying_key().serialize().map_err(|e| e.to_string())?))
}

fn run(op: &str, v: &Value) -> R<Value> {
    match op {
        "dkg1" => {
            let (max, min) = (u16_of(v, "max")?, u16_of(v, "min")?);
            let (secret, package) = dkg::part1(ident(u16_of(v, "id")?)?, max, min, OsRng).map_err(|e| e.to_string())?;
            Ok(json!({"secret": to(&secret)?, "package": to(&package)?}))
        }
        "dkg2" => {
            let secret: dkg::round1::SecretPackage = of(v, "secret")?;
            let packages: BTreeMap<Identifier, dkg::round1::Package> = map_of(v, "packages")?;
            let (s2, out) = dkg::part2(secret, &packages).map_err(|e| e.to_string())?;
            Ok(json!({"secret": to(&s2)?, "packages": map_to(&out, 16)?}))
        }
        "dkg3" => {
            let secret: dkg::round2::SecretPackage = of(v, "secret")?;
            let r1: BTreeMap<Identifier, dkg::round1::Package> = map_of(v, "round1")?;
            let r2: BTreeMap<Identifier, dkg::round2::Package> = map_of(v, "round2")?;
            let (kp, public) = dkg::part3(&secret, &r1, &r2).map_err(|e| e.to_string())?;
            Ok(json!({"key_package": to(&kp)?, "public": to(&public)?, "group_key": group_key(&public)?}))
        }
        "dealer" => {
            let (max, min) = (u16_of(v, "max")?, u16_of(v, "min")?);
            let (shares, public) = frost::keys::generate_with_dealer(max, min, frost::keys::IdentifierList::Default, OsRng)
                .map_err(|e| e.to_string())?;
            let mut kps = BTreeMap::new();
            for (id, s) in shares {
                kps.insert(id, frost::keys::KeyPackage::try_from(s).map_err(|e| e.to_string())?);
            }
            Ok(json!({"shares": map_to(&kps, max)?, "public": to(&public)?, "group_key": group_key(&public)?}))
        }
        "commit" => {
            let kp: frost::keys::KeyPackage = of(v, "key_package")?;
            let (nonces, commitments) = frost::round1::commit(kp.signing_share(), &mut OsRng);
            Ok(json!({"nonces": to(&nonces)?, "commitments": to(&commitments)?}))
        }
        "package" => {
            let commitments: BTreeMap<Identifier, frost::round1::SigningCommitments> = map_of(v, "commitments")?;
            let sp = frost::SigningPackage::new(commitments, &hexb(v, "message")?);
            Ok(json!({"signing_package": to(&sp)?}))
        }
        "sign" => {
            let kp: frost::keys::KeyPackage = of(v, "key_package")?;
            let nonces: frost::round1::SigningNonces = of(v, "nonces")?;
            let sp: frost::SigningPackage = of(v, "signing_package")?;
            // the signer signs only the message it checked itself, never what the coordinator put in the package
            if sp.message().as_slice() != hexb(v, "message")?.as_slice() {
                return Err("the signing package's message is not the verdict digest this referee checked".into());
            }
            let share = frost::round2::sign(&sp, &nonces, &kp).map_err(|e| e.to_string())?;
            Ok(json!({"share": to(&share)?}))
        }
        "aggregate" => {
            let sp: frost::SigningPackage = of(v, "signing_package")?;
            let shares: BTreeMap<Identifier, frost::round2::SignatureShare> = map_of(v, "shares")?;
            let public: frost::keys::PublicKeyPackage = of(v, "public")?;
            let sig = frost::aggregate(&sp, &shares, &public).map_err(|e| e.to_string())?;
            public.verifying_key().verify(sp.message(), &sig).map_err(|e| e.to_string())?;
            let bytes = sig.serialize().map_err(|e| e.to_string())?;
            Ok(json!({"signature": hex::encode(bytes), "group_key": group_key(&public)?}))
        }
        "verify" => {
            let key = frost::VerifyingKey::deserialize(&hexb(v, "group_key")?).map_err(|e| e.to_string())?;
            let sig = frost::Signature::deserialize(&hexb(v, "signature")?).map_err(|e| e.to_string())?;
            Ok(json!({"ok": key.verify(&hexb(v, "message")?, &sig).is_ok()}))
        }
        "info" => {
            let public: frost::keys::PublicKeyPackage = of(v, "public")?;
            let mut ids: Vec<u16> = Vec::new();
            for id in public.verifying_shares().keys() {
                ids.push(num(id, 16)?);
            }
            Ok(json!({"group_key": group_key(&public)?, "ids": ids, "min": public.min_signers()}))
        }
        _ => Err(format!("unknown operation {op}: dkg1 dkg2 dkg3 dealer commit package sign aggregate verify info")),
    }
}

fn main() {
    let op = std::env::args().nth(1).unwrap_or_default();
    let mut input = String::new();
    let out = std::io::stdin()
        .read_to_string(&mut input)
        .map_err(|e| e.to_string())
        .and_then(|_| serde_json::from_str::<Value>(if input.trim().is_empty() { "{}" } else { &input }).map_err(|e| e.to_string()))
        .and_then(|v| run(&op, &v));
    match out {
        Ok(v) => println!("{v}"),
        Err(e) => {
            println!("{}", json!({"error": e}));
            std::process::exit(2);
        }
    }
}
