# Decisions — Live QA Engineer

## T4-D1: `scrub_forbidden` returns the offender list, does NOT auto-substitute

**Context**: The plan offers two options for the scrubber:
(a) silently replace forbidden words with a plain-English equivalent, or
(b) remove them and return the list of found words so the caller can
decide.

**Decision**: Option (b).

**Rationale**:
- The plan's MUST NOT DO clause explicitly forbids "auto-replace
  forbidden words with silent substitutions" — it would hide the LLM's
  mistake and let the LLM drift toward more jargon over time.
- Returning the offender list lets the orchestrator: reject and retry,
  fall back to a template, log the LLM's misuse, or charge it against
  a quality score. All four reactions need the list.
- The plain-English glossary is still useful — it is injected into the
  system prompt so the LLM self-corrects on the next attempt. But the
  scrubber is a backstop, not a translator.

## T4-D2: `enforce_word_budget` uses greedy "include-as-many-fit" semantics

**Context**: "Truncate at sentence boundary if over budget" leaves room
for interpretation. The plan's QA test for T4 (with `max_words=4` and
2-word sentences) expects `'First sentence.'` (1 sentence); a natural
greedy reading would return `'First sentence. Second sentence.'` (2
sentences, exactly 4 words).

**Decision**: Greedy (include as many complete sentences as fit).

**Rationale**:
- The authoritative acceptance criterion #3 (`'a. b. c. d.'` max=2 →
  `'a. b.'`) is the contract. Greedy satisfies it.
- The plan's QA scenario #2 expects a non-greedy answer that no
  consistent reading can produce. We follow AC#3 (the spec) and document
  the QA discrepancy in `issues.md`.
- A budget function that stops one sentence short of fitting the budget
  is surprising behavior — every caller would have to set `max_words+1`
  to get the full budget.

## T4-D3: Plurals are in `FORBIDDEN_WORDS`, not derived at runtime

**Context**: The plan said "detect plural forms via lowercase substring".
Two implementation paths:
(a) Keep singular words only in `FORBIDDEN_WORDS`; at scrub time, append
`'s'` to each word and check both forms.
(b) Enumerate plurals explicitly in `FORBIDDEN_WORDS`.

**Decision**: Option (b).

**Rationale**:
- `VOCABULARY_GLOSSARY` must map EVERY forbidden word (singular + plural)
  to a plain-English phrase. Option (a) would require synthesising
  plural glossary entries on the fly, which the plan's third QA scenario
  (full coverage check) would flag.
- Option (b) is more explicit and matches the "data, not behavior"
  principle in the module docstring.
- The downside (12 extra strings in the set) is negligible.
