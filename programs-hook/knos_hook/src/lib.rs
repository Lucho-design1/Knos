//! knos-hook: Knos's Token-2022 transfer hook for PROJECT CREDITS (a Token-2022 mint with the TransferHook extension
//! pointing here). A credit moves only into a token account whose owner is the one its rules name: the project's escrow,
//! so credits pledged to a milestone cannot leave the milestone flow. Any other transfer fails the whole transaction.
//!
//! It speaks the SPL Transfer Hook Interface (spl-transfer-hook-interface), written out by hand so the program depends on
//! solana-program alone:
//!
//!   InitializeExtraAccountMetaList  data = [43,34,13,49,167,88,235,235] | allowed_owner (32)
//!       accounts: [validation PDA ["extra-account-metas", mint] (w), mint, mint authority (signer, w: pays rent),
//!                  system program, rules PDA ["rules", mint] (w)]
//!       Creates the validation account (one TLV entry for Execute listing ONE extra account: the rules PDA, as a fixed
//!       address) and the rules account (allowed_owner). Only the mint's authority may do it (checked by the caller's
//!       signature on the mint authority the client passes; the mint's own authority field is read and compared).
//!   Execute                         data = [105,37,101,197,75,251,102,26] | amount (u64 LE)
//!       accounts (as Token-2022 passes them): [source, mint, destination, owner, validation PDA, rules PDA]
//!       Fails with Custom(1) unless the destination token account's owner is the rules' allowed_owner.
//!
//! ERRORS (Custom): 0 bad instruction, 1 destination not allowed, 2 wrong validation or rules address, 3 not the mint's
//!   authority, 4 already initialised.

use solana_program::{
    account_info::{next_account_info, AccountInfo},
    entrypoint::ProgramResult,
    program::invoke_signed,
    program_error::ProgramError,
    pubkey::Pubkey,
    rent::Rent,
    system_instruction,
    sysvar::Sysvar,
};

pub const EXECUTE: [u8; 8] = [105, 37, 101, 197, 75, 251, 102, 26];
pub const INIT_METAS: [u8; 8] = [43, 34, 13, 49, 167, 88, 235, 235];
pub const VALIDATION_SEED: &[u8] = b"extra-account-metas";
pub const RULES_SEED: &[u8] = b"rules";
/// the validation account: TLV [Execute discriminator 8][length u32 4][PodSlice count u32 4][ExtraAccountMeta 35]
pub const VALIDATION_LEN: usize = 8 + 4 + 4 + 35;
/// the rules account: version u8 = 1 | allowed_owner 32
pub const RULES_LEN: usize = 1 + 32;

#[cfg(not(feature = "no-entrypoint"))]
solana_program::entrypoint!(process);

fn err(code: u32) -> ProgramError {
    ProgramError::Custom(code)
}

pub fn process(program_id: &Pubkey, accounts: &[AccountInfo], data: &[u8]) -> ProgramResult {
    if data.len() < 8 {
        return Err(err(0));
    }
    let (tag, rest) = data.split_at(8);
    if tag == EXECUTE {
        execute(program_id, accounts, rest)
    } else if tag == INIT_METAS {
        init(program_id, accounts, rest)
    } else {
        Err(err(0))
    }
}

fn execute(program_id: &Pubkey, accounts: &[AccountInfo], rest: &[u8]) -> ProgramResult {
    if rest.len() < 8 {
        return Err(err(0));
    }
    let it = &mut accounts.iter();
    let _source = next_account_info(it)?;
    let mint = next_account_info(it)?;
    let destination = next_account_info(it)?;
    let _owner = next_account_info(it)?;
    let validation = next_account_info(it)?;
    let rules = next_account_info(it)?;
    let (v, _) = Pubkey::find_program_address(&[VALIDATION_SEED, mint.key.as_ref()], program_id);
    let (r, _) = Pubkey::find_program_address(&[RULES_SEED, mint.key.as_ref()], program_id);
    if *validation.key != v || *rules.key != r || rules.owner != program_id {
        return Err(err(2));
    }
    let rd = rules.try_borrow_data()?;
    if rd.len() < RULES_LEN || rd[0] != 1 {
        return Err(err(2));
    }
    let allowed = &rd[1..33];
    // a Token-2022 token account: mint 0..32, owner 32..64
    let dd = destination.try_borrow_data()?;
    if dd.len() < 64 || &dd[0..32] != mint.key.as_ref() || &dd[32..64] != allowed {
        return Err(err(1));
    }
    Ok(())
}

fn init(program_id: &Pubkey, accounts: &[AccountInfo], rest: &[u8]) -> ProgramResult {
    if rest.len() < 32 {
        return Err(err(0));
    }
    let it = &mut accounts.iter();
    let validation = next_account_info(it)?;
    let mint = next_account_info(it)?;
    let authority = next_account_info(it)?;
    let system = next_account_info(it)?;
    let rules = next_account_info(it)?;
    if !authority.is_signer {
        return Err(err(3));
    }
    // the mint's authority (a Token-2022 mint: COption<Pubkey> at 0..36, tag u32 LE then the key)
    let md = mint.try_borrow_data()?;
    if md.len() < 36 || md[0..4] != [1, 0, 0, 0] || &md[4..36] != authority.key.as_ref() {
        return Err(err(3));
    }
    drop(md);
    let (v, vb) = Pubkey::find_program_address(&[VALIDATION_SEED, mint.key.as_ref()], program_id);
    let (r, rb) = Pubkey::find_program_address(&[RULES_SEED, mint.key.as_ref()], program_id);
    if *validation.key != v || *rules.key != r {
        return Err(err(2));
    }
    if validation.lamports() > 0 || rules.lamports() > 0 {
        return Err(err(4));
    }
    let rent = Rent::get()?;
    for (acct, len, seed, bump) in [(validation, VALIDATION_LEN, VALIDATION_SEED, vb), (rules, RULES_LEN, RULES_SEED, rb)] {
        invoke_signed(
            &system_instruction::create_account(authority.key, acct.key, rent.minimum_balance(len), len as u64, program_id),
            &[authority.clone(), acct.clone(), system.clone()],
            &[&[seed, mint.key.as_ref(), &[bump]]],
        )?;
    }
    {
        let mut vd = validation.try_borrow_mut_data()?;
        vd[0..8].copy_from_slice(&EXECUTE);
        vd[8..12].copy_from_slice(&(4u32 + 35).to_le_bytes());
        vd[12..16].copy_from_slice(&1u32.to_le_bytes());
        vd[16] = 0; // ExtraAccountMeta discriminator 0: a fixed address
        vd[17..49].copy_from_slice(r.as_ref());
        vd[49] = 0; // is_signer
        vd[50] = 0; // is_writable
    }
    let mut rd = rules.try_borrow_mut_data()?;
    rd[0] = 1;
    rd[1..33].copy_from_slice(&rest[0..32]);
    Ok(())
}
