//! knos_zk in LiteSVM with the committed fixture proof (zk/fixtures/score64).
use litesvm::LiteSVM;
use serde_json::Value;
use solana_keypair::Keypair;
use solana_program::{
    instruction::{AccountMeta, Instruction, InstructionError},
    pubkey::Pubkey,
    system_program,
};
use solana_signer::Signer;
use solana_transaction::Transaction;
use solana_transaction_error::TransactionError;
use std::path::PathBuf;

const Q: [u8; 32] = [
    0x30, 0x64, 0x4e, 0x72, 0xe1, 0x31, 0xa0, 0x29, 0xb8, 0x50, 0x45, 0xb6, 0x81, 0x81, 0x58, 0x5d, 0x97, 0x81, 0x6a,
    0x91, 0x68, 0x71, 0xca, 0x8d, 0x3c, 0x20, 0x8c, 0x16, 0xd8, 0x7c, 0xfd, 0x47,
];
const R: [u8; 32] = [
    0x30, 0x64, 0x4e, 0x72, 0xe1, 0x31, 0xa0, 0x29, 0xb8, 0x50, 0x45, 0xb6, 0x81, 0x81, 0x58, 0x5d, 0x28, 0x33, 0xe8,
    0x48, 0x79, 0xb9, 0x70, 0x91, 0x43, 0xe1, 0xf5, 0x93, 0xf0, 0x00, 0x00, 0x01,
];

fn root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}
fn fixture(name: &str) -> Value {
    serde_json::from_str(&std::fs::read_to_string(root().join("zk/fixtures/score64").join(name)).unwrap()).unwrap()
}
fn hx(v: &Value) -> Vec<u8> {
    hex::decode(v.as_str().unwrap()).unwrap()
}
/// q - y, big-endian
fn neg_y(y: &[u8]) -> Vec<u8> {
    if y.iter().all(|b| *b == 0) {
        return y.to_vec();
    }
    let mut out = vec![0u8; 32];
    let mut borrow = 0i16;
    for i in (0..32).rev() {
        let mut d = Q[i] as i16 - y[i] as i16 - borrow;
        borrow = if d < 0 { d += 256; 1 } else { 0 };
        out[i] = d as u8;
    }
    out
}

struct Proof {
    a_neg: Vec<u8>,
    b: Vec<u8>,
    c: Vec<u8>,
    inputs: Vec<u8>,
}
fn proof() -> Proof {
    let p = fixture("proof.json");
    let a = hx(&p["a"]);
    let mut a_neg = a[..32].to_vec();
    a_neg.extend(neg_y(&a[32..]));
    let inputs = fixture("public.json")["inputs"].as_array().unwrap().iter().flat_map(|v| hx(v)).collect();
    Proof { a_neg, b: hx(&p["b"]), c: hx(&p["c"]), inputs }
}
impl Proof {
    fn body(&self) -> Vec<u8> {
        [&self.a_neg[..], &self.b, &self.c, &self.inputs].concat()
    }
    fn verdict(&self, program: &Pubkey) -> (Pubkey, u8) {
        let t = &self.inputs[64 + 30..96];
        Pubkey::find_program_address(&[b"verdict", &self.inputs[..32], &self.inputs[32..64], t], program)
    }
}

struct Env {
    svm: LiteSVM,
    program: Pubkey,
    payer: Keypair,
}
fn env() -> Env {
    let so = std::env::var_os("KNOS_ZK_SO").map(PathBuf::from).expect("KNOS_ZK_SO = path of the built knos_zk.so");
    let mut svm = LiteSVM::new();
    let program = Pubkey::new_unique();
    svm.add_program_from_file(program, &so).unwrap();
    let payer = Keypair::new();
    svm.airdrop(&payer.pubkey(), 10_000_000_000).unwrap();
    Env { svm, program, payer }
}

fn budget(units: u32) -> Instruction {
    let mut data = vec![2u8];
    data.extend(units.to_le_bytes());
    Instruction::new_with_bytes("ComputeBudget111111111111111111111111111111".parse().unwrap(), &data, vec![])
}

/// sends one instruction (with a 1.4M limit); Ok(program's own CU) or the instruction error
fn send(e: &mut Env, ix: Instruction) -> Result<u64, InstructionError> {
    let tx = Transaction::new_signed_with_payer(
        &[budget(1_400_000), ix],
        Some(&e.payer.pubkey()),
        &[&e.payer],
        e.svm.latest_blockhash(),
    );
    let pid = e.program.to_string();
    let own = |logs: &[String]| -> u64 {
        logs.iter()
            .find_map(|l| {
                l.strip_prefix(&format!("Program {pid} consumed "))
                    .and_then(|r| r.split(' ').next())
                    .and_then(|n| n.parse().ok())
            })
            .unwrap_or(0)
    };
    let out = e.svm.send_transaction(tx);
    e.svm.expire_blockhash();
    match out {
        Ok(meta) => Ok(own(&meta.logs)),
        Err(f) => match f.err {
            TransactionError::InstructionError(1, ie) => Err(ie),
            other => panic!("unexpected {other:?} {:?}", f.meta.logs),
        },
    }
}

fn verify_ix(e: &Env, body: Vec<u8>) -> Instruction {
    Instruction::new_with_bytes(e.program, &[&[0u8][..], &body].concat(), vec![])
}
fn record_ix(e: &Env, p: &Proof, verdict: Pubkey, bump: u8) -> Instruction {
    Instruction::new_with_bytes(
        e.program,
        &[&[1u8, bump][..], &p.body()].concat(),
        vec![
            AccountMeta::new(e.payer.pubkey(), true),
            AccountMeta::new(verdict, false),
            AccountMeta::new_readonly(system_program::id(), false),
        ],
    )
}

#[test]
fn real_proof_verifies_and_tampered_proofs_are_refused() {
    let mut e = env();
    let p = proof();
    let cu_verify = send(&mut e, verify_ix(&e, p.body())).expect("the fixture proof must verify");
    assert!(cu_verify > 0 && cu_verify < 1_400_000);

    let refused = InstructionError::Custom(1);
    // one bit flipped in A, B, C, each public input
    for (name, off) in [("A", 63usize), ("B", 64 + 127), ("C", 192 + 63), ("spec_hash", 256 + 31), ("pred_hash", 288 + 31), ("threshold", 320 + 31)] {
        let mut body = p.body();
        body[off] ^= 1;
        let got = send(&mut e, verify_ix(&e, body));
        assert!(got.is_err(), "tampered {name} accepted");
        if name != "A" && name != "B" && name != "C" {
            assert_eq!(got.unwrap_err(), refused, "tampered {name}");
        }
    }
    // A without the negation
    let p2 = fixture("proof.json");
    let body = [&hx(&p2["a"])[..], &p.b, &p.c, &p.inputs].concat();
    assert_eq!(send(&mut e, verify_ix(&e, body)), Err(refused.clone()));
    // a public input at or above the group order r (r itself)
    let mut body = p.body();
    body[256..288].copy_from_slice(&R);
    assert_eq!(send(&mut e, verify_ix(&e, body)), Err(refused.clone()));
    // short data
    assert_eq!(send(&mut e, verify_ix(&e, p.body()[..300].to_vec())), Err(InstructionError::Custom(0)));

    // record
    let (verdict, bump) = p.verdict(&e.program);
    let cu_record = send(&mut e, record_ix(&e, &p, verdict, bump)).expect("record");
    let acct = e.svm.get_account(&verdict).unwrap();
    assert_eq!(acct.owner, e.program);
    assert_eq!(acct.data.len(), 138);
    assert_eq!(acct.data[0], 1);
    assert_eq!(&acct.data[2..98], &p.inputs[..]);
    assert_eq!(&acct.data[106..138], e.payer.pubkey().as_ref());
    // twice: refused
    assert_eq!(send(&mut e, record_ix(&e, &p, verdict, bump)), Err(InstructionError::Custom(3)));
    // another address
    let other = Pubkey::new_unique();
    assert_eq!(send(&mut e, record_ix(&e, &p, other, bump)), Err(InstructionError::Custom(2)));
    // a false statement (a bar the proof was not made for) records nothing
    let mut lower = proof();
    lower.inputs[95] = 0x2f; // a bar of 47 instead of 48: the proof was made for 48
    let (v2, b2) = lower.verdict(&e.program);
    assert!(send(&mut e, record_ix(&e, &lower, v2, b2)).is_err());
    assert!(e.svm.get_account(&v2).map_or(true, |a| a.lamports == 0));

    let out = serde_json::json!({
        "verify_cu": cu_verify,
        "verify_and_record_cu": cu_record,
        "public_inputs": 3,
        "where": "LiteSVM 0.7.1 (solana 2.x crates), program built by cargo-build-sbf 2.3.13",
    });
    println!("{out}");
    if let Some(path) = std::env::var_os("KNOS_ZK_CU_OUT") {
        std::fs::write(path, out.to_string()).unwrap();
    }
}
