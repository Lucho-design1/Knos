//! knos-zk: "the submission scored at least the bar on the sealed hidden test set", checked on chain without the set.
//!
//! The proof is Groth16 over BN254 (zk/score_circuit, arkworks); this program checks it with groth16-solana, which
//! calls Solana's alt_bn128 syscalls (G1 add, G1 mul, pairing). The verifying key is compiled in (src/vk.rs, written
//! by zk/score_circuit). The key comes from a TOY setup with a fixed seed: anyone can recompute its toxic waste and
//! forge proofs, so this build is for devnet and tests only. A build that pays real money needs a key from a
//! multi-party setup ceremony (docs/reference/ZK.md).
//!
//! PUBLIC INPUTS (3 x 32 bytes, big-endian scalars, each below the BN254 group order or the proof is refused):
//!   spec_hash  MiMC commitment to the sealed hidden labels + salt, committed before the work
//!   pred_hash  MiMC commitment to the submission's predictions + salt
//!   threshold  the bar (count of predictions equal to their label), < 2^16
//!
//! INSTRUCTIONS (first byte):
//!   0 Verify            data = 0 | A_neg (64) | B (128) | C (64) | inputs (96)        no accounts
//!       A_neg is the proof's A with y negated (q - y), the form the pairing check e(-A,B)e(L,g)e(C,d)e(a,b) = 1 reads.
//!       Fails the transaction unless the proof verifies. Return data = the 96 input bytes.
//!   1 VerifyAndRecord   data = 1 | bump | A_neg | B | C | inputs
//!       accounts: [payer signer writable, verdict writable, system program]
//!       verdict = PDA ["verdict", spec_hash, pred_hash, threshold (last 2 bytes, big-endian)]. Verifies, then
//!       creates the verdict account (rent from payer). A payout that requires "a verified proof for this spec and
//!       this submission at this bar" checks that this account exists and is owned by this program.
//!
//! VERDICT ACCOUNT (138 bytes): version u8 = 1 | bump u8 | spec_hash 32 | pred_hash 32 | threshold 32 |
//!   slot u64 LE | recorder pubkey 32.
//!
//! ERRORS (Custom): 0 bad instruction data, 1 proof refused, 2 wrong verdict address, 3 verdict already recorded,
//!   4 wrong system program.

use groth16_solana::groth16::Groth16Verifier;
use solana_program::{
    account_info::{next_account_info, AccountInfo},
    clock::Clock,
    entrypoint::ProgramResult,
    msg,
    program::{invoke, invoke_signed, set_return_data},
    program_error::ProgramError,
    pubkey::Pubkey,
    rent::Rent,
    system_instruction, system_program,
    sysvar::Sysvar,
};

pub mod vk;

pub const PROOF_LEN: usize = 64 + 128 + 64;
pub const INPUTS_LEN: usize = 32 * vk::NR_PUBLIC_INPUTS;
pub const VERDICT_LEN: usize = 1 + 1 + INPUTS_LEN + 8 + 32;
pub const VERDICT_SEED: &[u8] = b"verdict";

pub const E_DATA: u32 = 0;
pub const E_PROOF: u32 = 1;
pub const E_ADDRESS: u32 = 2;
pub const E_RECORDED: u32 = 3;
pub const E_SYSTEM: u32 = 4;

#[cfg(not(feature = "no-entrypoint"))]
solana_program::entrypoint!(process_instruction);

fn err(code: u32) -> ProgramError {
    ProgramError::Custom(code)
}

/// verify proof || inputs; returns the inputs
pub fn verify(body: &[u8]) -> Result<[[u8; 32]; vk::NR_PUBLIC_INPUTS], ProgramError> {
    if body.len() != PROOF_LEN + INPUTS_LEN {
        return Err(err(E_DATA));
    }
    let a: &[u8; 64] = body[..64].try_into().unwrap();
    let b: &[u8; 128] = body[64..192].try_into().unwrap();
    let c: &[u8; 64] = body[192..256].try_into().unwrap();
    let mut inputs = [[0u8; 32]; vk::NR_PUBLIC_INPUTS];
    for (i, chunk) in body[PROOF_LEN..].chunks_exact(32).enumerate() {
        inputs[i].copy_from_slice(chunk);
    }
    let mut v = Groth16Verifier::new(a, b, c, &inputs, &vk::VERIFYINGKEY).map_err(|_| err(E_DATA))?;
    v.verify().map_err(|_| err(E_PROOF))?;
    Ok(inputs)
}

pub fn process_instruction(program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    match data.first() {
        Some(0) => {
            verify(&data[1..])?;
            set_return_data(&data[1 + PROOF_LEN..]);
            msg!("knos_zk: proof verified");
            Ok(())
        }
        Some(1) => {
            if data.len() < 2 {
                return Err(err(E_DATA));
            }
            let bump = data[1];
            let inputs = verify(&data[2..])?;
            let it = &mut accounts.iter();
            let payer = next_account_info(it)?;
            let verdict = next_account_info(it)?;
            let system = next_account_info(it)?;
            if !payer.is_signer {
                return Err(ProgramError::MissingRequiredSignature);
            }
            if *system.key != system_program::id() {
                return Err(err(E_SYSTEM));
            }
            let t = [inputs[2][30], inputs[2][31]];
            let seeds: &[&[u8]] = &[VERDICT_SEED, &inputs[0], &inputs[1], &t, &[bump]];
            let expect = Pubkey::create_program_address(seeds, program_id).map_err(|_| err(E_ADDRESS))?;
            if expect != *verdict.key {
                return Err(err(E_ADDRESS));
            }
            if verdict.owner != &system_program::id() || !verdict.data_is_empty() {
                return Err(err(E_RECORDED));
            }
            // allocate + assign, topping rent up first: an address someone funded in advance is still usable
            let need = Rent::get()?.minimum_balance(VERDICT_LEN).saturating_sub(verdict.lamports());
            if need > 0 {
                invoke(
                    &system_instruction::transfer(payer.key, verdict.key, need),
                    &[payer.clone(), verdict.clone(), system.clone()],
                )?;
            }
            invoke_signed(
                &system_instruction::allocate(verdict.key, VERDICT_LEN as u64),
                &[verdict.clone(), system.clone()],
                &[seeds],
            )?;
            invoke_signed(
                &system_instruction::assign(verdict.key, program_id),
                &[verdict.clone(), system.clone()],
                &[seeds],
            )?;
            let mut d = verdict.try_borrow_mut_data()?;
            d[0] = 1;
            d[1] = bump;
            for (i, inp) in inputs.iter().enumerate() {
                d[2 + 32 * i..2 + 32 * (i + 1)].copy_from_slice(inp);
            }
            let o = 2 + INPUTS_LEN;
            d[o..o + 8].copy_from_slice(&Clock::get()?.slot.to_le_bytes());
            d[o + 8..o + 40].copy_from_slice(payer.key.as_ref());
            set_return_data(&data[2 + PROOF_LEN..]);
            msg!("knos_zk: proof verified, verdict recorded");
            Ok(())
        }
        _ => Err(err(E_DATA)),
    }
}
