//! The same Montgomery arithmetic as rsa.rs, on 64-bit limbs (v0.3.29). A 2048-bit number is 32 limbs here and 64
//! there, so a squaring does a quarter of the multiplications.
//!
//! WHERE IT IS FAST. A 64 x 64 -> 128-bit product is two instructions on sBPF v2 (`lmul64` for the low half and
//! `uhmul64` for the high half: the PQR instruction class of SIMD-0174). On sBPF v0/v1 and on the v3 of Agave 4.4
//! (no `uhmul64`) the same Rust compiles to a call into compiler-rt's `__multi3`, which costs more than four 32-bit
//! products. So a v2 build uses `mont_mul`/`mont_sqr` below; a v3 build (v0.3.30) the same functions in `h` (four
//! inline 32 x 32 -> 64-bit `mul64`s on halves loaded as 32-bit words); build.rs picks; v0/v1 keep rsa.rs.
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

#[cfg(not(knos_mulhi32))] #[inline(always)]
fn mac(t: u64, a: u64, b: u64, c: u64) -> (u64, u64) {
    // t + a b + c < 2^128: (2^64 - 1)^2 + 2 (2^64 - 1) = 2^128 - 1
    let s = t as u128 + (a as u128) * (b as u128) + c as u128;
    (s as u64, (s >> 64) as u64)
}

/// out = a b R^-1 mod n, for a, b < n (CIOS). `t` is scratch of at least l + 2 limbs.
#[cfg(not(knos_mulhi32))] pub fn mont_mul(out: &mut [u64], a: &[u64], b: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
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
#[cfg(not(knos_mulhi32))] pub fn mont_sqr(out: &mut [u64], a: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
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

/// The same two functions for an sBPF without `uhmul64` (the v3 of Agave 4.4, build.rs: `knos_mulhi32`; v0.3.30).
/// The limbs, rows and reductions are those above, 64 bits wide; only each t + a b + c is made from four 32 x 32 ->
/// 64-bit products, and its 32-bit halves are loaded and stored as 32-bit words (one `ldxw`/`stxw` each, a little-
/// endian u64 being its two u32 halves in order) instead of being cut out of a u64 with shifts. A u128 product there
/// would be a call into compiler-rt's `__multi3`. No sum in `mac_h` can overflow its u64 (bounds beside it), so it has
/// no carry tests, and it uses wrapping operations so the release profile's overflow checks add nothing.
#[cfg(knos_mulhi32)]
pub use h::{mont_mul_h as mont_mul, mont_sqr_h as mont_sqr};

#[cfg(any(knos_mulhi32, test))]
mod h {
    use super::{geq, sub_in};
    const M: u64 = 0xffff_ffff;

    /// (out0, out1) = halves of the low u64 of t + a b + c (t = t0 + 2^32 t1, b = b0 + 2^32 b1, a = a0 + 2^32 a1);
    /// returns the high u64. `o` may be `i` or two words below it: t is read before anything is written.
    #[inline(always)]
    unsafe fn mac_h(i: *const u32, o: *mut u32, b: *const u32, a0: u64, a1: u64, c: u64) -> u64 {
        let (b0, t0) = (*b as u64, *i as u64);
        // s0 = a0 b0 + t0 + c0 <= (2^32 - 1)^2 + 2 (2^32 - 1) = 2^64 - 1
        let s0 = a0.wrapping_mul(b0).wrapping_add(t0).wrapping_add(c & M);
        let p10 = a1.wrapping_mul(b0);
        let (b1, t1) = (*b.add(1) as u64, *i.add(1) as u64);
        *o = s0 as u32;
        // s1 = a0 b1 + t1 + (s0 >> 32): same bound
        let s1 = a0.wrapping_mul(b1).wrapping_add(t1).wrapping_add(s0 >> 32);
        // s2 = a1 b0 + (s1 mod 2^32) + c1: same bound
        let s2 = p10.wrapping_add(s1 & M).wrapping_add(c >> 32);
        *o.add(1) = s2 as u32;
        // t + a b + c = (s0 mod 2^32) + 2^32 (s2 mod 2^32) + 2^64 (a1 b1 + (s1 >> 32) + (s2 >> 32)) < 2^128
        a1.wrapping_mul(b1).wrapping_add(s1 >> 32).wrapping_add(s2 >> 32)
    }

    /// For j < len: limb j of `o` = low u64 of (limb j of `i`) + a (limb j of `b`) + carry; returns the last carry.
    #[inline(always)]
    unsafe fn row(i: *const u32, o: *mut u32, b: *const u32, len: usize, a: u64, mut c: u64) -> u64 {
        let (a0, a1) = (a & M, a >> 32);
        for j in 0..len { c = mac_h(i.add(2 * j), o.add(2 * j), b.add(2 * j), a0, a1, c); }
        c
    }

    pub fn mont_mul_h(out: &mut [u64], a: &[u64], b: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
        let l = n.len();
        // never true (Pow sizes every buffer): it fails closed, a zero power matches no signature
        if l == 0 || a.len() < l || b.len() < l || t.len() < l + 2 || out.len() < l { out.fill(0); return; }
        let t = &mut t[..l + 2];
        for v in t.iter_mut() { *v = 0; }
        let (bp, np) = (b.as_ptr() as *const u32, n.as_ptr() as *const u32);
        for &ai in a[..l].iter() {
            let tp = t.as_mut_ptr() as *mut u32;
            // SAFETY: t has l + 2 limbs, b and n at least l (checked above); a row touches limbs 0..l of each.
            let c = unsafe { row(tp, tp, bp, l, ai, 0) };
            let (s, o) = t[l].overflowing_add(c);
            t[l] = s;
            t[l + 1] = o as u64;
            let m = t[0].wrapping_mul(n0inv);
            let tp = t.as_mut_ptr() as *mut u32;
            // limb 0 of t + m n is 0 by the choice of m: only its carry is kept (written to a scratch word pair)
            let mut z = [0u32; 2];
            // SAFETY: as above; the shifted row reads limbs 1..l of t and writes limbs 0..l-1, each read before it is
            // written.
            let c = unsafe {
                let c = mac_h(tp, z.as_mut_ptr(), np, m & M, m >> 32, 0);
                row(tp.add(2), tp, np.add(2), l - 1, m, c)
            };
            let (s, o) = t[l].overflowing_add(c);
            t[l - 1] = s;
            t[l] = t[l + 1].wrapping_add(o as u64);
            t[l + 1] = 0;
        }
        out[..l].copy_from_slice(&t[..l]);
        if t[l] != 0 || geq(&out[..l], n) { sub_in(&mut out[..l], n); }
    }

    pub fn mont_sqr_h(out: &mut [u64], a: &[u64], n: &[u64], n0inv: u64, t: &mut [u64]) {
        let l = n.len();
        // never true, as in mont_mul_h: fails closed
        if l == 0 || a.len() < l || t.len() < 2 * l + 1 || out.len() < l { out.fill(0); return; }
        let t = &mut t[..2 * l + 1];
        for v in t.iter_mut() { *v = 0; }
        let (ap, np) = (a.as_ptr() as *const u32, n.as_ptr() as *const u32);
        for i in 0..l {
            let tp = t.as_mut_ptr() as *mut u32;
            // SAFETY: the row covers limbs 2i+1 .. i+l of t (< 2l) and i+1 .. l of a.
            let c = unsafe { row(tp.add(2 * (2 * i + 1)), tp.add(2 * (2 * i + 1)), ap.add(2 * (i + 1)), l - i - 1, a[i], 0) };
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
            // t[2i] + a_i^2 + c, then its high half into t[2i + 1] with the carry out
            let tp = t.as_mut_ptr() as *mut u32;
            // SAFETY: limbs 2i and 2i + 1 < 2l of t, limb i of a.
            let hi = unsafe { mac_h(tp.add(4 * i), tp.add(4 * i), ap.add(2 * i), a[i] & M, a[i] >> 32, c) };
            let (s, o) = t[2 * i + 1].overflowing_add(hi);
            t[2 * i + 1] = s;
            c = o as u64;
        }
        let mut hi = 0u64;
        for i in 0..l {
            let m = t[i].wrapping_mul(n0inv);
            let tp = t.as_mut_ptr() as *mut u32;
            // SAFETY: limbs i .. i+l-1 < 2l of t, all l limbs of n.
            let c = unsafe { row(tp.add(2 * i), tp.add(2 * i), np, l, m, 0) };
            let (s, o1) = t[i + l].overflowing_add(c);
            let (s, o2) = s.overflowing_add(hi);
            t[i + l] = s;
            hi = (o1 as u64) + (o2 as u64);
        }
        out[..l].copy_from_slice(&t[l..2 * l]);
        if hi != 0 || geq(&out[..l], n) { sub_in(&mut out[..l], n); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rsa;

    #[test]
    fn the_32_bit_halves_arithmetic_is_the_u128_arithmetic() {
        let mut seed = 0x0123_4567_89ab_cdefu64;
        let r64 = |s: &mut u64| (rnd(s) as u64) << 32 | rnd(s) as u64;
        for l in [1usize, 2, 3, 8, 32, 64] {
            for k in 0..30 {
                let mut n: Vec<u64> = (0..l).map(|_| r64(&mut seed)).collect();
                n[0] |= 1;
                n[l - 1] |= 1 << 63;
                let edge = k % 3 == 0;
                // a, b < n; every third case uses limbs of all ones below the top (the largest carries)
                let mut a: Vec<u64> = (0..l).map(|_| if edge { u64::MAX } else { r64(&mut seed) }).collect();
                let mut b: Vec<u64> = (0..l).map(|_| r64(&mut seed)).collect();
                a[l - 1] = n[l - 1] - 1;
                b[l - 1] &= 0x7fff_ffff_ffff_ffff;
                let n0 = n0inv64(n[0]);
                let mut t = vec![0u64; 2 * l + 2];
                let (mut m1, mut m2, mut s1, mut s2) = (vec![0u64; l], vec![0u64; l], vec![0u64; l], vec![0u64; l]);
                mont_mul(&mut m1, &a, &b, &n, n0, &mut t);
                h::mont_mul_h(&mut m2, &a, &b, &n, n0, &mut t);
                assert_eq!(m1, m2, "mul l={l} k={k}");
                mont_sqr(&mut s1, &a, &n, n0, &mut t);
                h::mont_sqr_h(&mut s2, &a, &n, n0, &mut t);
                assert_eq!(s1, s2, "sqr l={l} k={k}");
            }
        }
    }

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
