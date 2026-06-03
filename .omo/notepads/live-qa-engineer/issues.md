# Issues — Live QA Engineer

## T4-1: Plan QA scenario for `enforce_word_budget` has an inconsistent expected output

**Severity**: Plan bug (does not block T4 acceptance criteria).
**Discovered**: 2026-06-03 during T4 implementation.

### Symptom
The plan at `.omo/plans/live-qa-engineer.md` (T4, "QA Scenarios" section,
"Word budget truncates at sentence") asserts:

```python
out = enforce_word_budget('First sentence. Second sentence. Third sentence.', max_words=4)
assert out == 'First sentence.'
```

But the *other* acceptance criterion (T4, "Acceptance Criteria" #3) asserts:

```python
enforce_word_budget('a. b. c. d.', max_words=2) == 'a. b.'
```

These two assertions are inconsistent with each other. There is no
sensible reading of "truncate at sentence boundary if over budget" that
satisfies both:

| Input                                | max_words | AC says       | QA says          |
| ------------------------------------ | --------- | ------------- | ---------------- |
| `'a. b. c. d.'` (1-word sentences)   | 2         | `'a. b.'`     | n/a              |
| `'First sentence. Second. Third.'`   | 4         | (2-word sents)| `'First sentence.'` |
| `'First sentence. Second. Third.'`   | 2         | n/a           | `'First sentence.'` (passes naturally) |

The QA scenario's expected output `'First sentence.'` would only be
correct if the test had been written with `max_words=2` (which would make
the second 2-word sentence overflow and stop after the first 2-word
sentence). With `max_words=4` and 2-word sentences, the natural answer
is the first two sentences = 4 words = `max_words` exactly.

### Resolution
- **Implementation kept natural** (greedy: include as many complete
  sentences as fit within the budget).
- The **authoritative acceptance criterion #3 passes**.
- The plan's QA scenario test fails by design; the failure is documented
  in `.omo/evidence/T4-budget.txt` with full output and a counterfactual
  check (`max_words=2` returns `'First sentence.'` as the plan expects).
- Recommend: either fix the plan's QA test to use `max_words=2`, or
  rewrite AC#3 to use a multi-word-sentence case that distinguishes the
  "stop at sentence boundary" semantics from "stop one sentence earlier".

### Status
Not a blocker for T4. Recorded for the plan owner. No code change.
