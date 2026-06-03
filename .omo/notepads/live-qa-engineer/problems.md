# Problems — Live QA Engineer

## T4-P1: Plan QA scenario #2 (enforce_word_budget) conflicts with acceptance criterion #3

See `issues.md` T4-1 for the full writeup.

Short version: the plan's expected output for the budget QA scenario is
inconsistent with its own acceptance criterion. The implementation follows
the acceptance criterion; the QA scenario fails by design. Failure is
documented in `.omo/evidence/T4-budget.txt` with a counterfactual check
showing the QA test would pass if `max_words` were 2 instead of 4.

**No code change** is the correct action. The plan owner should fix the
typo or rewrite one of the two tests for consistency.
