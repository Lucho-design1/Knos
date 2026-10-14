//! The committed fixtures verify with groth16-solana (the verifier the program runs, here on its native path), every
//! tampered proof or input is refused, and a submission below the bar cannot be proven.
use ark_bn254::{Bn254, Fr, G1Affine};
use ark_groth16::Groth16;
use ark_relations::r1cs::{ConstraintSynthesizer, ConstraintSystem};
use ark_snark::SNARK;
use ark_std::rand::{rngs::StdRng, SeedableRng};
use groth16_solana::groth16::{Groth16Verifier, Groth16Verifyingkey};
use knos_zk_score::*;

fn fixture(name: &str) -> serde_json::Value {
    let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../fixtures/score64").join(name);
    serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap()
}
fn h<const N: usize>(v: &serde_json::Value) -> [u8; N] {
    hex::decode(v.as_str().unwrap()).unwrap().try_into().unwrap()
}
/// -A: y -> q - y (big-endian)
fn neg_g1(a: &[u8; 64]) -> [u8; 64] {
    use ark_ff::{BigInteger, PrimeField};
    let y = ark_bn254::Fq::from_be_bytes_mod_order(&a[32..]);
    let mut out = *a;
    let ny = (-y).into_bigint().to_bytes_be();
    out[32..].copy_from_slice(&ny);
    out
}

struct Fx {
    a: [u8; 64],
    b: [u8; 128],
    c: [u8; 64],
    inputs: [[u8; 32]; 3],
    alpha: [u8; 64],
    beta: [u8; 128],
    gamma: [u8; 128],
    delta: [u8; 128],
    ic: Vec<[u8; 64]>,
}
fn load() -> Fx {
    let vk = fixture("vk.json");
    let pr = fixture("proof.json");
    let pu = fixture("public.json");
    let ins: Vec<[u8; 32]> = pu["inputs"].as_array().unwrap().iter().map(h::<32>).collect();
    Fx {
        a: h(&pr["a"]),
        b: h(&pr["b"]),
        c: h(&pr["c"]),
        inputs: ins.try_into().unwrap(),
        alpha: h(&vk["alpha_g1"]),
        beta: h(&vk["beta_g2"]),
        gamma: h(&vk["gamma_g2"]),
        delta: h(&vk["delta_g2"]),
        ic: vk["ic"].as_array().unwrap().iter().map(h::<64>).collect(),
    }
}
fn check(f: &Fx) -> bool {
    let vk = Groth16Verifyingkey {
        nr_pubinputs: 3,
        vk_alpha_g1: f.alpha,
        vk_beta_g2: f.beta,
        vk_gamme_g2: f.gamma,
        vk_delta_g2: f.delta,
        vk_ic: &f.ic,
    };
    let a = neg_g1(&f.a);
    match Groth16Verifier::new(&a, &f.b, &f.c, &f.inputs, &vk) {
        Ok(mut v) => v.verify().is_ok(),
        Err(_) => false,
    }
}

#[test]
fn fixture_proof_verifies_with_groth16_solana() {
    assert!(check(&load()));
}

#[test]
fn fixture_public_inputs_are_the_sample_hashes() {
    let s = synthetic_sample(SAMPLE_N, SAMPLE_CORRECT, SAMPLE_THRESHOLD);
    let f = load();
    let p = s.public_inputs();
    for i in 0..3 {
        assert_eq!(fr_be(&p[i]), f.inputs[i]);
    }
}

#[test]
fn tampered_proofs_and_inputs_are_refused() {
    let base = load();
    // flip one bit in each part of the proof
    for part in 0..3 {
        let mut f = load();
        match part {
            0 => f.a[63] ^= 1,
            1 => f.b[127] ^= 1,
            _ => f.c[63] ^= 1,
        }
        assert!(!check(&f), "tampered proof part {part} accepted");
    }
    // a lower threshold, another spec hash, another submission hash
    for i in 0..3 {
        let mut f = load();
        f.inputs[i][31] ^= 1;
        assert!(!check(&f), "tampered public input {i} accepted");
    }
    // the proof's own A without the negation the verifier expects
    let vk = Groth16Verifyingkey {
        nr_pubinputs: 3,
        vk_alpha_g1: base.alpha,
        vk_beta_g2: base.beta,
        vk_gamme_g2: base.gamma,
        vk_delta_g2: base.delta,
        vk_ic: &base.ic,
    };
    let mut v = Groth16Verifier::new(&base.a, &base.b, &base.c, &base.inputs, &vk).unwrap();
    assert!(v.verify().is_err());
    // swapped A and C
    let mut f = load();
    std::mem::swap(&mut f.a, &mut f.c);
    assert!(!check(&f));
}

#[test]
fn below_the_bar_cannot_be_proven() {
    // 52 of 64 right; a bar of 53 has no satisfying witness
    let s = synthetic_sample(SAMPLE_N, SAMPLE_CORRECT, 53);
    let cs = ConstraintSystem::<Fr>::new_ref();
    s.generate_constraints(cs.clone()).unwrap();
    assert!(!cs.is_satisfied().unwrap());
    // exactly at the bar is fine
    let s = synthetic_sample(SAMPLE_N, SAMPLE_CORRECT, SAMPLE_CORRECT as u64);
    let cs = ConstraintSystem::<Fr>::new_ref();
    s.generate_constraints(cs.clone()).unwrap();
    assert!(cs.is_satisfied().unwrap());
}

#[test]
fn a_proof_for_another_circuit_size_does_not_fit() {
    // a different (small) circuit's proof under the fixture key: refused
    let s = synthetic_sample(4, 4, 3);
    let mut rng = StdRng::seed_from_u64(1);
    let (pk, _vk) = Groth16::<Bn254>::circuit_specific_setup(s.clone(), &mut rng).unwrap();
    let proof = Groth16::<Bn254>::prove(&pk, s.clone(), &mut rng).unwrap();
    let mut f = load();
    f.a = g1_be(&proof.a);
    f.b = g2_be(&proof.b);
    f.c = g1_be(&proof.c);
    let p = s.public_inputs();
    for i in 0..3 {
        f.inputs[i] = fr_be(&p[i]);
    }
    assert!(!check(&f));
    let _ = G1Affine::default();
}
