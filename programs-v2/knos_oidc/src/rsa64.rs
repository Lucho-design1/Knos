//! The same Montgomery arithmetic as rsa.rs, on 64-bit limbs (v0.3.29). A 2048-bit number is 32 limbs here and 64
//! there, so a squaring does a quarter of the multiplications.
//!
//! WHY IT IS FAST ONLY ON sBPF v2. A 64 x 64 -> 128-bit product is two instructions on sBPF v2 (`lmul64`
//! for the low half and `uhmul64` for the high half: the PQR instruction class of SIMD-0174). On sBPF v0/v1 the same
//! Rust compiles to a call into compiler-rt's `__multi3`, which costs more than four 32-bit products. So the program
//! uses this module only in a build for an sBPF v2 target (build.rs sets `knos_pqr`), and natively (tests). The sBPF v3
//! of Agave 4.4 has no `uhmul64` either, so a v3 build keeps rsa.rs.
//!
//! Numbers are little-endian u64 limbs. The bytes of a little-endian u64 limb are the bytes of two little-endian u32
//! limbs in the same order, so what `store` writes into a token account is byte for byte what rsa::store writes for
//! the same number: a token account started under one build can be finished under the other.
//! R is the same as rsa.rs's (2^(32 l32) = 2^(64 l64)), so the key account's r2 serves both.

pub fn load(d: &[u8], out: &mut [u64]) {
    for (i, o) in out.iter_mut().enumerate() { *o = u64::from_le_bytes(d[8 * i..8 * i + 8].try_into().unwrap()); }
}
pub fn store(d: &mut [u8], x: &[u64]) {
    for (i, v) in x.iter().enumerate() { d[8 * i..8 * i + 8].copy_from_slice(&v.to_le_bytes()); }
}
/// u32 limbs (rsa.rs's) to u64 limbs: limb i is lo | hi << 32.
pub fn from32(x: &[u32], out: &mut [u64]) {
    for (i, o) in out.iter_mut().enumerate() { *o = x[2 * i] as u64 | (x[2 * i + 1] as u64) << 32; }
}
pub fn to32(x: &[u64], out: &mut [u32]) {
    for (i, v) in x.iter().enumerate() { out[2 * i] = *v as u32; out[2 * i + 1] = (*v >> 32) as u32; }
}
/// -n0^-1 mod 2^64, for an odd n0. Newton: n0 is its own inverse modulo 8 (3 correct bits) and each step doubles the
/// correct bits, so five steps give 96 >= 64.
pub fn n0inv64(n0: u64) -> u64 {
    let mut inv = n0;
    for _ in 0..5 { inv = inv.wrapping_mul(2u64.wrapping_sub(n0.wrapping_mul(inv))); }
    inv.wrapping_neg()
}
pub fn geq(a: &[u64], b: &[u64]) -> bool {
    for i in (0..b.len()).rev() {
        if a[i] != b[i] { return a[i] > b[i]; }
    }
    true
}
pub fn sub_in(a: &mut [u64], b: &[u64]) {
    let mut borrow = 0u64;
    for (x, y) in a.iter_mut().zip(b.iter()) {
        let (d1, o1) = x.overflowing_sub(*y);
        let (d2, o2) = d1.overflowing_sub(borrow);
        *x = d2;
        borrow = (o1 | o2) as u64;
    }
}

#[inline(always)]
fn mac(t: u64, a: u64, b: u64, c: u64) -> (u64, u64) {
    // t + a b + c < 2^128: (2^64 - 1)^2 + 2 (2^64 - 1) = 2^128 - 1
    let s = t as u128 + (a as u128) * (b as u128) + c as u128;
    (s as u64, (s >> 64) as u64)
}

/// out = a b R^-1 mod n, for a, b < n (CIOS). `t` is scratch of at least l + 2 limbs.
pub fn mont_mul(out: &mut [u64], a: &[u64], b: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
    let l = n.len();
    let t = &mut t[..l + 2];
    for v in t.iter_mut() { *v = 0; }
    for &ai in a[..l].iter() {
        let mut c = 0u64;
        for (tj, &bj) in t[..l].iter_mut().zip(b[..l].iter()) {
            let (lo, hi) = mac(*tj, ai, bj, c);
            *tj = lo;
            c = hi;
        }
        let s = t[l] as u128 + c as u128;
        t[l] = s as u64;
        t[l + 1] = (s >> 64) as u64;
        let m = t[0].wrapping_mul(n0inv);
        let (_, mut c) = mac(t[0], m, n[0], 0);
        for j in 1..l {
            let (lo, hi) = mac(t[j], m, n[j], c);
            t[j - 1] = lo;
            c = hi;
        }
        let s = t[l] as u128 + c as u128;
        t[l - 1] = s as u64;
        t[l] = t[l + 1].wrapping_add((s >> 64) as u64);
        t[l + 1] = 0;
    }
    out[..l].copy_from_slice(&t[..l]);
    if t[l] != 0 || geq(&out[..l], n) { sub_in(&mut out[..l], n); }
}

/// out = a^2 R^-1 mod n for a < n: each cross product once, doubled, the squares added, one reduction.
/// `t` is scratch of at least 2 l + 1 limbs.
pub fn mont_sqr(out: &mut [u64], a: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
    let l = n.len();
    let t = &mut t[..2 * l + 1];
    for v in t.iter_mut() { *v = 0; }
    for i in 0..l {
        let ai = a[i];
        let mut c = 0u64;
        for (tj, &aj) in t[2 * i + 1..i + l].iter_mut().zip(a[i + 1..l].iter()) {
            let (lo, hi) = mac(*tj, ai, aj, c);
            *tj = lo;
            c = hi;
        }
        t[i + l] = c;
    }
    let mut top = 0u64;
    for v in t[..2 * l].iter_mut() {
        let w = *v;
        *v = (w << 1) | top;
        top = w >> 63;
    }
    let mut c = 0u64;
    for i in 0..l {
        let d = (a[i] as u128) * (a[i] as u128);
        let s = t[2 * i] as u128 + (d as u64) as u128 + c as u128;
        t[2 * i] = s as u64;
        let s = t[2 * i + 1] as u128 + (d >> 64) + (s >> 64);
        t[2 * i + 1] = s as u64;
        c = (s >> 64) as u64;
    }
    let mut hi = 0u64;
    for i in 0..l {
        let m = t[i].wrapping_mul(n0inv);
        let mut c = 0u64;
        for (tj, &nj) in t[i..i + l].iter_mut().zip(n.iter()) {
            let (lo, h) = mac(*tj, m, nj, c);
            *tj = lo;
            c = h;
        }
        let s = t[i + l] as u128 + c as u128 + hi as u128;
        t[i + l] = s as u64;
        hi = (s >> 64) as u64;
    }
    out[..l].copy_from_slice(&t[l..2 * l]);
    if hi != 0 || geq(&out[..l], n) { sub_in(&mut out[..l], n); }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rsa;

    fn rnd(seed: &mut u64) -> u32 { *seed ^= *seed << 13; *seed ^= *seed >> 7; *seed ^= *seed << 17; *seed as u32 }

    #[test]
    fn the_64_bit_arithmetic_is_the_32_bit_arithmetic_byte_for_byte() {
        let mut seed = 0x9e37_79b9_7f4a_7c15u64;
        for l32 in [64usize, 128] {
            for _ in 0..20 {
                let mut n: Vec<u32> = (0..l32).map(|_| rnd(&mut seed)).collect();
                n[0] |= 1; n[l32 - 1] |= 0x8000_0000;
                let mut a: Vec<u32> = (0..l32).map(|_| rnd(&mut seed)).collect();
                let mut b: Vec<u32> = (0..l32).map(|_| rnd(&mut seed)).collect();
                a[l32 - 1] &= 0x7fff_ffff; b[l32 - 1] &= 0x7fff_ffff; // below n
                let mut inv: u32 = 1;
                for _ in 0..5 { inv = inv.wrapping_mul(2u32.wrapping_sub(n[0].wrapping_mul(inv))); }
                let n0 = inv.wrapping_neg();
                let mut t = vec![0u32; 2 * l32 + 2];
                let (mut m32, mut s32) = (vec![0u32; l32], vec![0u32; l32]);
                rsa::mont_mul(&mut m32, &a, &b, &n, n0, &mut t);
                rsa::mont_sqr(&mut s32, &a, &n, n0, &mut t);
                let l = l32 / 2;
                let (mut n64, mut a64, mut b64) = (vec![0u64; l], vec![0u64; l], vec![0u64; l]);
                from32(&n, &mut n64); from32(&a, &mut a64); from32(&b, &mut b64);
                let n0_64 = n0inv64(n64[0]);
                assert_eq!(n0_64 as u32, n0);
                let mut t64 = vec![0u64; 2 * l + 2];
                let (mut m64, mut s64) = (vec![0u64; l], vec![0u64; l]);
                mont_mul(&mut m64, &a64, &b64, &n64, n0_64, &mut t64);
                mont_sqr(&mut s64, &a64, &n64, n0_64, &mut t64);
                // different R per limb width? no: R = 2^(32 l32) = 2^(64 l) in both, so the results are equal
                let (mut mb, mut sb) = (vec![0u8; 4 * l32], vec![0u8; 4 * l32]);
                store(&mut mb, &m64); store(&mut sb, &s64);
                let (mut mb32, mut sb32) = (vec![0u8; 4 * l32], vec![0u8; 4 * l32]);
                rsa::store(&mut mb32, &m32); rsa::store(&mut sb32, &s32);
                assert_eq!(mb, mb32);
                assert_eq!(sb, sb32);
            }
        }
    }
}
