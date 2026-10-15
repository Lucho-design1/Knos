//! The ORCID reader (0.3.34): a researcher's ORCID iD is paid at a wallet, as a GitHub account is. Bind (8) takes an
//! ORCID id_token in a GitHub claim token's place (pay.rs `bind`): the same accounts, the same marker, the same rule that
//! a Bind is replaced only by a later token. Then any order's proof or verdict can name the researcher by iD
//! ("0000-0002-1825-0097.10000.-") and the money goes to the wallet the iD bound, with no GitHub account at all.
//!
//! What ORCID signs (OpenID Connect, https://orcid.org/.well-known/openid-configuration fetched 14 Oct 2026: issuer
//! https://orcid.org, id_token_signing_alg_values_supported ["RS256"], one RSA-2048 key at https://orcid.org/oauth/jwks;
//! claims and lifetime from ORCID's guide, github.com/ORCID/ORCID-Source orcid-web/ORCID_AUTH_WITH_OPENID_CONNECT.md,
//! read 14 Oct 2026): `sub` the iD, `aud` the client id that asked, `nonce` as the client sent it, `iat`, `exp`
//! (its example is 24 hours after `iat`), `auth_time`, `jti`.
//!
//! THE BINDING. Knos's sign-in page asks ORCID for an id_token with nonce "knos3:bind:<wallet address>". The token is
//! taken only when:
//!   - its family is ORCID (issuers.rs: a key registered for https://orcid.org through knos-oidc's attested path; a
//!     private key is never ORCID), fresh, its key still usable;
//!   - `aud` is one of ORCID_CLIENTS: Knos's own registered ORCID client. Any other client could have chosen the nonce
//!     itself, so a token for another site (where a person signed in with ORCID) binds nothing here;
//!   - `sub` is a well-formed iD with a good check character; `nonce` names a wallet;
//!   - `iat` is at most TOKEN_AHEAD ahead and `exp` at most ORCID_LIFE after it;
//!   - and its `iat` is later than the one the iD's Bind holds (a Bind is replaced only by a later sign-in).
//!     The token's marker ["used", sig] is made as for every token, and is kept until the token cannot be fresh any more.
use crate::{err, issuers::{self, Family}, E_AUD, E_CLAIMS, E_TOKEN, TOKEN_AHEAD};
use knos_oidc::claims::{self, fields, number, parts, text};
use solana_program::{account_info::AccountInfo, program_error::ProgramError, pubkey::Pubkey};

/// Bind's question (pay.rs): is this an ORCID id_token? None for every other account, which Bind then reads as a
/// GitHub claim token exactly as before (and refuses as before). Some: the sign-in, read through the one front door.
pub fn of(tok: &AccountInfo, key: &AccountInfo, now: i64) -> Result<Option<Orcid>, ProgramError> {
    if issuers::family_of(tok) != Some(Family::Orcid) { return Ok(None); }
    issuers::checked(tok, key, now, |_, f, _| f == Family::Orcid, |_, payload, exp| read(payload, exp, now)).map(Some)
}

/// How long a used ORCID token's marker must stay (state::mark_used keeps it for an hour's token): until it cannot be
/// fresh, exp + knos_oidc::LATE, and an hour more.
pub fn keep_until(exp: i64) -> i64 { exp.saturating_add(knos_oidc::LATE + 3600) }

/// ORCID's id_token lives 24 hours in its own example (exp - iat = 86,400).
pub const ORCID_LIFE: i64 = 86_400;

/// The ORCID client ids whose sign-ins bind. EMPTY in a real build until the founder registers Knos's ORCID client
/// (a public API client, https://orcid.org/developer-tools) and pins its id here: until then BindOrcid binds nothing.
/// A testkeys build pins a test client id.
#[cfg(feature = "testkeys")]
pub const ORCID_CLIENTS: &[&[u8]] = &[b"APP-KNOSTEST00000001"];
#[cfg(not(feature = "testkeys"))]
pub const ORCID_CLIENTS: &[&[u8]] = &[];

pub struct Orcid { pub id: u64, pub iat: i64, pub exp: i64, pub wallet: Pubkey }

/// knos3:bind:<address>
pub fn bind_nonce(nonce: &[u8]) -> Result<Pubkey, ProgramError> {
    let [k, b, address] = parts::<3>(nonce).ok_or_else(|| err(E_AUD))?;
    if k != b"knos3" || b != b"bind" { return Err(err(E_AUD)); }
    Ok(Pubkey::new_from_array(claims::b58_32(address).ok_or_else(|| err(E_AUD))?))
}

/// The claims of a verified ORCID id_token, as BindOrcid judges them.
pub fn read(payload: &[u8], exp: i64, now: i64) -> Result<Orcid, ProgramError> {
    let [sub, aud, nonce, iat] = fields(payload, [b"sub", b"aud", b"nonce", b"iat"])?;
    let iat = number(iat)? as i64;
    if iat > now.saturating_add(TOKEN_AHEAD) || exp.saturating_sub(iat) > ORCID_LIFE { return Err(err(E_TOKEN)); }
    let aud = text(aud)?;
    if !ORCID_CLIENTS.iter().any(|c| *c == &aud[..]) { return Err(err(E_AUD)); }
    let id = issuers::orcid_id(&text(sub)?).ok_or_else(|| err(E_CLAIMS))?;
    Ok(Orcid { id, iat, exp, wallet: bind_nonce(&text(nonce)?)? })
}


#[cfg(test)]
mod tests {
    use super::*;

    fn token(over: &[(&str, &str)]) -> Vec<u8> {
        let w = Pubkey::new_from_array([9; 32]);
        let nonce = format!("\"knos3:bind:{w}\"");
        let mut c: Vec<(&str, String)> = vec![("aud", "\"APP-KNOSTEST00000001\"".into()), ("sub", "\"0000-0002-1825-0097\"".into()), ("auth_time", "999".into()),
            ("iss", "\"https:\\/\\/orcid.org\"".into()), ("exp", "87400".into()), ("iat", "1000".into()), ("nonce", nonce), ("jti", "\"j\"".into())];
        for (k, v) in over { c.iter_mut().find(|e| e.0 == *k).unwrap().1 = v.to_string(); }
        format!("{{{}}}", c.iter().map(|(k, v)| format!("\"{k}\":{v}")).collect::<Vec<_>>().join(",")).into_bytes()
    }

    #[test]
    fn an_orcid_sign_in_to_knos_names_the_id_and_the_wallet() {
        if ORCID_CLIENTS.is_empty() {
            // a real build: nothing binds until the founder pins Knos's ORCID client
            assert!(read(&token(&[]), 87_400, 1000).err() == Some(err(E_AUD)));
            return;
        }
        let o = read(&token(&[]), 87_400, 1000).ok().unwrap();
        assert_eq!((o.id, o.iat, o.wallet), (issuers::OR_BASE + 21_825_009, 1000, Pubkey::new_from_array([9; 32])));
        for (k, v, want) in [("aud", "\"APP-OTHERCLIENT00001\"", E_AUD), ("sub", "\"0000-0002-1825-0098\"", E_CLAIMS), ("nonce", "\"knos3:take:x\"", E_AUD),
                             ("nonce", "\"n1\"", E_AUD), ("iat", "1301", E_TOKEN), ("sub", "21825009", 63)] {
            assert!(read(&token(&[(k, v)]), 87_400, 1000).err() == Some(err(want)), "{k} {v}");
        }
        assert!(read(&token(&[]), 1000 + ORCID_LIFE + 1, 1000).err() == Some(err(E_TOKEN)));
    }
}
