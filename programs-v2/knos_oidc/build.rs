//! Sets `knos_pqr` when the target is sBPF v2 (cargo build-sbf --arch v2), whose PQR instructions (SIMD-0174) make a
//! 64 x 64 -> 128-bit product two instructions (`lmul64`, `uhmul64`): modexp.rs then uses 64-bit limbs (rsa64.rs).
//! NOT for sBPF v3: the v3 that Agave 4.4 runs (SIMD-0178, SIMD-0189, SIMD-0377) has no `uhmul64` (a v3 build of
//! platform-tools v1.57 holds `mul64` and no `uhmul64`), so a 128-bit product is emulated and 64-bit limbs are slower
//! than 32-bit ones there: measured in docs/reference/PLATFORM.md.
fn main() {
    println!("cargo:rustc-check-cfg=cfg(knos_pqr)");
    println!("cargo:rerun-if-env-changed=TARGET");
    let target = std::env::var("TARGET").unwrap_or_default();
    if target.starts_with("sbpfv2-") {
        println!("cargo:rustc-cfg=knos_pqr");
    }
}
