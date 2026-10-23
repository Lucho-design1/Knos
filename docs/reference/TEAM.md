# Who builds Knos

Knos carries research across the valley of death: each step is paid only on verified proof.

Everything below the first section is a plan, and no part of it is a fact.

## Today: one person

Each line is said once here, with what would change it.

| today | what would change it |
|---|---|
| **One founder, pseudonymous:** the GitHub account [drexthealpha](https://github.com/drexthealpha). No legal name is published. | The founder publishes a name, or a second person is named here. |
| **No co-founder,** employee, adviser or contractor. | A person joins and agrees to be named on this page. |
| **No legal entity.** | A company is formed; its name and registration are printed here. |
| **No legal advice taken.** | A lawyer is engaged; [REGULATION.md](REGULATION.md) says who and on what. |
| **No outside review** of the code, the workflows or the documents. | A reviewer publishes findings; [ASSURANCE.md](ASSURANCE.md) links them. |
| **Outside key holders today: 0.** All three member keys of both multisigs, the account the pinned workflows live in, and the relay are the founder's. | One person opens a "Key holder request" ([KEYHOLDER.md](KEYHOLDER.md)) and the founder runs one command ([GOVERNANCE.md](GOVERNANCE.md), section 5). |
| **No second operator.** | Someone else runs the checklist in [OPERATOR.md](OPERATOR.md) and its drill is recorded. |

He reviews, commits and answers for every change. [DISCLOSURE.md](DISCLOSURE.md), "How the code is written", lists
the tools he uses.

## What an outside key holder would do

A plan. **Nobody holds this role and nobody has been asked.** [KEYHOLDER.md](KEYHOLDER.md) is the page for the
person who would; [GOVERNANCE.md](GOVERNANCE.md), section 4, is the job in full. In short, an outside key holder:

- holds one member key of each multisig, on a device only they control, and is not paid by a buyer or a supplier;
- before voting for an upgrade, rebuilds the program from the proposed commit and compares the hash with the
  proposal's buffer, reads the gate record, reads the diff of the programs, and checks the tests at that commit;
- votes, or does not; and votes to cancel if something is wrong after approval;
- for the guardian, checks a new signing key against the issuer's own published key set before approving it;
- holds nobody's money: no member key can move an order.

One outside key of three gives a second pair of eyes and does not bind the founder, who would still hold two.
Two outside keys of three would. `node scripts/governance.mjs replace-member` prints which of the two a change
leads to before anything is proposed.

## From a personal account to an organisation account

This is a plan. **None of it has been done**, and its first step waits on a second person.

Today the pinned workflows, the key-rotation and claim workflows, the relay, the site and the source all live in
one personal GitHub account. If that account were suspended or lost, funded orders could only be refunded.

[GOVERNANCE.md](GOVERNANCE.md), section 9, has the steps with what changes in the pins and what a paying
repository must re-pin; [DEPENDENCY.md](DEPENDENCY.md) has what each step needs. In short:

1. Create a GitHub organisation with two owners, the founder and one other person, each with their own
   second factor, and move the source, the site and the releases there. This changes nothing on chain. One owner
   alone would change little: the organisation would depend on that one account as the personal account does now.
2. Publish the pinned workflows from the organisation, and have the programs accept a workflow pin under either
   owner for a period, so that orders funded under the old pin still pay. This is a program upgrade and passes
   through the public 8-day delay.
3. Move the rotation and claim workflows the same way.
4. Run the relay from the organisation, and a second relay somewhere that is not GitHub.
5. Remove the personal account from every pin once the last order funded under it is paid or refunded.
6. Put the multisig's keys in more than one person's hands before any real money moves.

Steps 3 and 5 need program changes that are not in this release.
