---
name: knos-goal
description: How to run a Knos goal token-efficiently in Claude Code (intent sketch, difficulty routing, batching, memory, Sibyl save/debloat). Use at the start of every Knos goal.
---

# Running a Knos goal

1. **Intent sketch first** (IDT I1/I10). Write ten lines before any edit: end state, files, checks that prove it,
   out of scope. The goal's own criteria are the success checks.
2. **Route by difficulty** (R4/R18). Routine edits: terse, no re-reading a file you just wrote, low effort.
   Reason deeply only on a failing test or a wrong live result.
3. **Drafts, not prose** (R3). Status lines are short drafts; no recaps of what was already said.
4. **Recall before re-deriving** (R6/R17). Search knos-mind and Sibyl (`memory_search`) for the fact first.
5. **Batch** (R21). Independent reads and commands go in one call.
6. **No overhead loops.** No subagents, worktrees or background watch loops; poll a run only for its result.
   `CLAUDE_CODE_GOAL_CHECKIN_MINUTES=0` keeps an idle goal from re-sending the whole context.
7. **Test output is trimmed** by the PreToolUse hook `~/.claude/hooks/trim_test_output.py` (failures and summary
   only); put `KNOS_FULL_TEST_OUTPUT=1` in the command for the full log.
8. **Lower `/effort` for routine steps**, `/clear` between unrelated tasks, specific prompts with a check to pass.
9. **End of goal:** run `/sibyl-save` then `/sibyl-debloat`, and report the memory size against the free plan's
   5,242,880-byte cap (`sibyl status`).
