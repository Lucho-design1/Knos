//! Picks the RSA arithmetic of an sBPF build (modexp.rs):
//!   - sBPF v2 (cargo build-sbf --arch v2): `knos_pqr` + `knos_wide`. Its PQR instructions (SIMD-0174) make a
//!     64 x 64 -> 128-bit product two instructions (`lmul64`, `uhmul64`): 64-bit limbs (rsa64.rs).
//!   - sBPF v3 (v0.3.30): `knos_wide` + `knos_mulhi32`. The v3 that Agave 4.4 runs (SIMD-0178, SIMD-0189, SIMD-0377)
//!     has no `uhmul64` (a u128 product there is a call into compiler-rt's `__multi3`), so the same 64-bit limbs make
//!     each 128-bit product from four 32 x 32 -> 64-bit `mul64`s, loading and storing 32-bit halves (rsa64::h).
//!   - sBPF v0 and v1: 32-bit limbs (rsa.rs).
//!
//! Measured in docs/reference/PLATFORM.md.
fn main() {
    println!("cargo:rustc-check-cfg=cfg(knos_pqr)");
    println!("cargo:rustc-check-cfg=cfg(knos_wide)");
    println!("cargo:rustc-check-cfg=cfg(knos_mulhi32)");
    println!("cargo:rerun-if-env-changed=TARGET");
    let target = std::env::var("TARGET").unwrap_or_default();
    if target.starts_with("sbpfv2-") {
        println!("cargo:rustc-cfg=knos_pqr");
        println!("cargo:rustc-cfg=knos_wide");
    } else if target.starts_with("sbpfv3-") {
        println!("cargo:rustc-cfg=knos_wide");
        println!("cargo:rustc-cfg=knos_mulhi32");
    }
}
