# CoParenTime Feature Roadmap (Bang-for-Buck Order)

Purpose: provide implementation-ready feature cards that can be spun into separate agent sessions.

Prioritization method:
- Benefit: user impact and planning quality improvement (1-5)
- Simplicity: implementation effort/risk, where 5 is easiest (1-5)
- Bang-for-buck score: Benefit x Simplicity

## Recommended Delivery Sequence

| Rank | Feature | Benefit | Simplicity | Bang-for-Buck | Include? |
|---|---|---:|---:|---:|---|
| 1 | Custom split target (default 50/50, configurable e.g. 70/30) | 5 | 4 | 20 | [x] |
| 2 | Adjustable weighting: couple-time vs fairness/even split | 5 | 3 | 15 | [x] |
| 3 | Copy result card as image (include or hide couple info) | 4 | 4 | 16 | [x] |
| 4 | Optional iCal/Google feed for other_parent exclusions | 4 | 3 | 12 | [x] |
| 5 | Optional iCal/Google feed for partner exclusions (enhance existing calendar support) | 3 | 4 | 12 | [x] |
| 6 | Lock specific dates to a parent before optimization (manual override pins) | 4 | 3 | 12 | [ ] |
| 7 | What-if comparison mode (A/B runs with side-by-side metrics) | 4 | 3 | 12 | [x] |
| 8 | School holiday preset manager (save/reuse holiday windows in UI) | 3 | 4 | 12 | [x] |
| 9 | Hard-constraint conflict explainer (why no feasible plan exists) | 4 | 2 | 8 | [x] |
| 10 | Export to .ics for both parents from chosen plan | 3 | 2 | 6 | [x] |

Notes:
- Item 5 is intentionally framed as an enhancement because the app already has calendar-based exclusion support; this extends it to explicit per-person semantics.
- Items 6-10 are suggested additional features. Keep checked/unchecked boxes as your scope control for future sessions.

---

## Feature Cards for Agent Sessions

### 1) Custom Split Target (50/50 default, user-configurable)
Problem solved:
- Fairness is not always an even split in real arrangements.

Goal:
- Support a configurable target split where first value is this_parent and second value is other_parent (e.g. 70/30, 25/75).

Scope:
- Add runtime config/input fields for target split.
- Validate total equals 100 and both values are in [0, 100].
- Update scoring/fairness gap calculations to compare against configured target.
- Reflect target split in audits and report text.

Acceptance criteria:
- Default behavior remains 50/50 when unset.
- Invalid split (sum != 100) returns actionable validation errors.
- Report clearly states target and achieved split.
- Existing tests still pass; new tests cover split math and validation.

Suggested implementation notes:
- Add config keys like split_this_parent_percent and split_other_parent_percent.
- Keep deterministic ranking unchanged except fairness target reference.

---

### 2) Adjustable Weighting: Couple Time vs Even Split
Problem solved:
- Users need to tune optimizer priorities by season or situation.

Goal:
- Allow configurable weighting between couple-time optimization and fairness target adherence.

Scope:
- Add weight controls in API/UI/config.
- Use weights in scoring engine in place of hardcoded balance.
- Persist selected weights into run input/audit for reproducibility.

Acceptance criteria:
- Defaults match current behavior if no custom weighting provided.
- Changing weights changes ranking predictably.
- Audit output shows effective weights used for each run.

Suggested implementation notes:
- Start with two top-level knobs: fairness_weight and couple_time_weight.
- Optionally keep transitions/fragmentation fixed in MVP.

---

### 3) Copy Result Card as Image (with optional couple-info redaction)
Problem solved:
- Users need a fast, shareable output without exposing sensitive relationship data.

Goal:
- One-click copy of the plan result card as PNG image with two modes:
  - Full card
  - Redacted card (couple information hidden)

Scope:
- Add client-side capture button(s) in result UI.
- Add redaction toggle for partner/couple-time sections before capture.
- Copy image to clipboard and show success/failure toast.

Acceptance criteria:
- Works in Chromium-based browsers and degrades gracefully when clipboard image is unavailable.
- Redacted mode excludes couple-time details from image.
- No server-side processing required.

Suggested implementation notes:
- Use a stable DOM capture approach and preserve existing theme/colors.
- Keep redaction visual explicit (e.g. section hidden or masked with label).

---

### 4) Optional iCal/Google URL for other_parent Exclusions
Problem solved:
- Constraints are incomplete if only one side calendar exclusions are represented.

Goal:
- Accept an optional calendar feed for other_parent and apply as hard exclusions.

Scope:
- Add config/input key for other_parent calendar URL.
- Parse feed into exclusion intervals normalized to Europe/London.
- Apply exclusions consistently in candidate feasibility checks.
- Show source attribution in audit (manual vs iCal).

Acceptance criteria:
- If URL is absent, behavior unchanged.
- If feed fetch fails, run continues with visible warning.
- Exclusion intervals are applied deterministically.

Suggested implementation notes:
- Reuse existing iCal adapter logic and redaction/sanitization patterns.
- Isolate source-specific parsing from core constraint logic.

---

### 5) Optional iCal/Google URL for Partner Exclusions (Enhanced)
Problem solved:
- Partner availability quality improves with direct calendar exclusions.

Goal:
- Add/normalize explicit partner calendar integration as optional exclusion source.

Scope:
- If current single calendar key exists, migrate to explicit per-actor keys while maintaining backward compatibility.
- Merge partner text exclusions and partner calendar exclusions into unified interval set.
- Keep warning banners and secure URL handling behavior.

Acceptance criteria:
- Existing config still works (no breaking change).
- New partner-specific URL key takes precedence when provided.
- Audit indicates which exclusions came from partner calendar.

Suggested implementation notes:
- Add migration mapping in config parser (legacy key -> partner key).
- Keep all URL token redaction rules in run artifact persistence.

---

## Suggested Optional Features (Include/Exclude)

Use this checklist to control scope:
- [ ] Include 6) Lock specific dates to a parent before optimization
- [ ] Include 7) What-if comparison mode (side-by-side run diff)
- [ ] Include 8) School holiday preset manager (create/save/reuse)
- [ ] Include 9) Hard-constraint conflict explainer when no feasible plan
- [ ] Include 10) Export selected schedule to .ics for each parent

Quick value notes:
- 6) Reduces negotiation friction with known immovable commitments.
- 7) Speeds decision-making by comparing tradeoffs objectively.
- 8) Saves repeated setup time each holiday period.
- 9) Improves trust when the engine rejects all candidates.
- 10) Improves downstream usability once plan is accepted.

---

## Suggested Agent Session Prompts

Use one prompt per feature:

1. "Implement roadmap item #1 in FEATURE_ROADMAP.md with tests, preserving deterministic behavior and backward compatibility."
2. "Implement roadmap item #2 in FEATURE_ROADMAP.md, including API/UI/config plumbing and scoring audit updates."
3. "Implement roadmap item #3 in FEATURE_ROADMAP.md with full and redacted image-copy modes and graceful browser fallback."
4. "Implement roadmap item #4 in FEATURE_ROADMAP.md using existing iCal adapter patterns and warning behavior."
5. "Implement roadmap item #5 in FEATURE_ROADMAP.md with legacy config compatibility and explicit partner-source auditing."

Definition of done for each session:
- Unit/integration tests updated or added.
- No regressions in existing behavior when feature is not enabled.
- README/config docs updated for any new keys/inputs.
- Run output/audit includes enough context for reproducibility.
