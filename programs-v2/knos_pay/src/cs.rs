//! The Google Confidential Space reader (0.3.34). A Confidential Space attestation token says that one container
//! image, named by its digest, ran in a hardened TEE that Google attested, and carries the audience the workload chose.
//! So an order can pin ITS JUDGE AS A CONTAINER IMAGE instead of a GitHub workflow: whoever runs that image in
//! Confidential Space (any GCP project: the funder, the researcher, a lab, Knos) gets a token that only that image's
//! code could have asked for, with the audience it chose: knos3:proof:<order>:<evidence>:<terms>:<payees>.
//!
//! What Google signs, per https://docs.cloud.google.com/confidential-computing/confidential-space/docs/reference/token-claims
//! (read 14 Oct 2026):
//!   iss          https://confidentialcomputing.googleapis.com (issuers::CS_ISSUER; RS256, keys RSA-2048 on 14 Oct 2026)
//!   aud          the workload's custom audience, at most 512 bytes
//!   iat, exp     numbers
//!   swname       "CONFIDENTIAL_SPACE" (a plain Confidential VM says "GCE": refused)
//!   dbgstat      "disabled-since-boot" in the production image ("enabled" in the debug image: refused)
//!   secboot      true
//!   hwmodel      GCP_AMD_SEV, GCP_AMD_SEV_ES, GCP_INTEL_TDX (GCP_SHIELDED_VM is not a TEE: refused)
//!   submods.container.image_digest                 "sha256:<64 hex>": the order's pin
//!   submods.confidential_space.support_attributes  must hold "STABLE" or "USABLE" (an EXPERIMENTAL-only image is refused)
//! LIFETIME. Google's pages give no lifetime; the launcher fetches its default token every hour. This reader takes a
//! token whose `exp` is at most TOKEN_LIFE (an hour) after its `iat`, and none whose `iat` is more than TOKEN_AHEAD ahead.
use crate::{err, issuers::{array_has, nested_text}, E_CLAIMS, E_TOKEN, TOKEN_AHEAD, TOKEN_LIFE};
use knos_oidc::claims::{self, fields, number, text};
use solana_program::program_error::ProgramError;

/// What PayOrder judges of a Confidential Space token.
pub struct Cs { pub iat: i64, pub aud: Vec<u8>, pub image_digest: [u8; 32] }

pub const HWMODELS: [&[u8]; 3] = [b"GCP_AMD_SEV", b"GCP_AMD_SEV_ES", b"GCP_INTEL_TDX"];

/// The claims of a verified Confidential Space token, or a refusal: E_TOKEN for its times, E_CLAIMS for anything that
/// is not a production Confidential Space container in a TEE, claims errors (63) for a claim missing or mistyped.
pub fn read(payload: &[u8], exp: i64, now: i64) -> Result<Cs, ProgramError> {
    let [iat, aud, swname, dbgstat, secboot, hwmodel, submods] = fields(payload,
        [b"iat", b"aud", b"swname", b"dbgstat", b"secboot", b"hwmodel", b"submods"])?;
    let iat = number(iat)? as i64;
    if iat > now.saturating_add(TOKEN_AHEAD) || exp.saturating_sub(iat) > TOKEN_LIFE { return Err(err(E_TOKEN)); }
    let tee = text(swname)? == b"CONFIDENTIAL_SPACE" && text(dbgstat)? == b"disabled-since-boot"
        && secboot.is_some_and(|r| !r.is_str && r.bytes == b"true") && HWMODELS.contains(&&text(hwmodel)?[..]);
    if !tee { return Err(err(E_CLAIMS)); }
    let sub = submods.filter(|r| !r.is_str).ok_or_else(|| err(claims::E_CLAIM))?.bytes;
    let digest = nested_text(sub, &[b"container", b"image_digest"])?;
    let [cs] = fields(sub, [b"confidential_space"])?;
    let [attrs] = fields(cs.filter(|r| !r.is_str).ok_or_else(|| err(E_CLAIMS))?.bytes, [b"support_attributes"])?;
    let attrs = attrs.filter(|r| !r.is_str).ok_or_else(|| err(E_CLAIMS))?.bytes;
    if !array_has(attrs, b"STABLE") && !array_has(attrs, b"USABLE") { return Err(err(E_CLAIMS)); }
    let hex = digest.strip_prefix(b"sha256:").ok_or_else(|| err(E_CLAIMS))?;
    let image_digest = claims::unhex32(hex).ok_or_else(|| err(E_CLAIMS))?;
    Ok(Cs { iat, aud: text(aud)?, image_digest })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn token(over: &[(&str, &str)]) -> Vec<u8> {
        let digest = format!("\"sha256:{}\"", "ab".repeat(32));
        let mut c: Vec<(&str, String)> = vec![("aud", "\"knos3:proof:x\"".into()), ("iat", "1000".into()), ("exp", "4600".into()), ("iss", "\"https://confidentialcomputing.googleapis.com\"".into()),
            ("swname", "\"CONFIDENTIAL_SPACE\"".into()), ("swversion", "[\"20260900\"]".into()), ("dbgstat", "\"disabled-since-boot\"".into()), ("secboot", "true".into()),
            ("hwmodel", "\"GCP_INTEL_TDX\"".into()), ("oemid", "11129".into()),
            ("submods", format!("{{\"container\":{{\"image_digest\":{digest},\"image_reference\":\"us-docker.pkg.dev/p/r/judge@sha256:x\"}},\"confidential_space\":{{\"support_attributes\":[\"LATEST\",\"STABLE\",\"USABLE\"]}},\"gce\":{{\"zone\":\"us-central1-a\"}}}}"))];
        for (k, v) in over { c.iter_mut().find(|e| e.0 == *k).unwrap().1 = v.to_string(); }
        format!("{{{}}}", c.iter().map(|(k, v)| format!("\"{k}\":{v}")).collect::<Vec<_>>().join(",")).into_bytes()
    }
    fn code(over: &[(&str, &str)]) -> Option<u32> {
        match read(&token(over), 4600, 1000) { Ok(_) => None, Err(ProgramError::Custom(c)) => Some(c), Err(_) => Some(0) }
    }

    #[test]
    fn a_production_confidential_space_container_is_read_by_its_image_digest() {
        let c = read(&token(&[]), 4600, 1000).ok().unwrap();
        assert_eq!((c.iat, c.image_digest, &c.aud[..]), (1000, [0xab; 32], &b"knos3:proof:x"[..]));
        for hw in ["GCP_AMD_SEV", "GCP_AMD_SEV_ES"] { assert_eq!(code(&[("hwmodel", &format!("\"{hw}\""))]), None); }
    }

    #[test]
    fn a_debug_image_a_plain_vm_and_anything_else_is_refused() {
        let sub = |digest: &str, attrs: &str| format!("{{\"container\":{{\"image_digest\":{digest}}},\"confidential_space\":{{\"support_attributes\":{attrs}}}}}");
        let good = format!("\"sha256:{}\"", "ab".repeat(32));
        for (k, v, want) in [("swname", "\"GCE\"".to_string(), E_CLAIMS), ("dbgstat", "\"enabled\"".into(), E_CLAIMS), ("secboot", "false".into(), E_CLAIMS),
                             ("secboot", "\"true\"".into(), E_CLAIMS), ("hwmodel", "\"GCP_SHIELDED_VM\"".into(), E_CLAIMS), ("iat", "1301".into(), E_TOKEN),
                             ("submods", sub(&good, "[\"EXPERIMENTAL\"]"), E_CLAIMS), ("submods", sub(&good, "[]"), E_CLAIMS),
                             ("submods", sub(&format!("\"sha512:{}\"", "ab".repeat(32)), "[\"STABLE\"]"), E_CLAIMS),
                             ("submods", sub(&format!("\"sha256:{}\"", "AB".repeat(32)), "[\"STABLE\"]"), E_CLAIMS),
                             ("submods", sub("null", "[\"STABLE\"]"), 63), ("submods", "\"x\"".into(), 63), ("aud", "7".into(), 63)] {
            assert_eq!(code(&[(k, &v)]), Some(want), "{k} {v}");
        }
        assert!(read(&token(&[]), 1000 + TOKEN_LIFE + 1, 1000).is_err());
        assert_eq!(code(&[("submods", &sub(&good, "[\"USABLE\"]"))]), None);
    }
}
