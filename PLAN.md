# Distributional Program Analysis (DPA) — Implementation Plan

A phased plan that takes the project from empty repository to NIER submission with results for the three pre-registered evaluation questions (cross-benchmark transfer, model-scale dependence, extension beyond functional correctness) plus the two open questions (prior collapse, false consensus). Designed for a single PhD student with periodic advisor input. Total estimated effort: **~12 weeks of focused work**, with parallelizable evaluation runs.

The plan is intentionally falsifiable at every phase: each milestone has an acceptance criterion that, if it fails, surfaces a problem early rather than at submission time.

---

## Phase 0 — Project setup (Week 0, ~3 days)

**Goal:** a clean repository, reproducible environment, and a tiny end-to-end smoke test before any real engineering.

### Steps

1. **Repository skeleton.** Create a Python package `dpa/` with submodules `sampler/`, `analyzer/`, `invariants/`, `posterior/`, `apps/`, `eval/`. Add `pyproject.toml`, lockfile, and a `tests/` mirror.
2. **Pinned environment.** Python 3.11, locked dependencies via `uv` or `poetry`. Pin the LLM client SDK to a specific version. Pin the abstract-interpretation back-end to a specific commit (Phase 2 chooses the tool).
3. **Reproducibility hygiene.** Single `make reproduce` target that, given a task id, produces a deterministic output (within LLM sampling stochasticity, fixed seed). All experiments write to `runs/<task_id>/<timestamp>/` with `config.json`, `samples/{0..N-1}.py`, `invariants/{0..N-1}.json`, `posterior.json`, `result.json`.
4. **Smoke test.** Run end-to-end on the `rolling_max(xs, k)` example from the paper: sample N=5 programs from a small open-weight model, run the analyzer, compute survival, dump posterior. No quality target—just plumbing.

### Acceptance criterion
`make smoketest` produces a populated `runs/smoketest/` in under 60 seconds with N=5 samples.

### Risks
- Underestimating the cost of running an analyzer per sample. **Mitigation:** measure analyzer wall-time on the smoke test first; if it's >5s per program on simple Python, switch back-ends before committing.

---

## Phase 1 — Sampling pipeline (Week 1, ~5 working days)

**Goal:** a deterministic, cache-aware pipeline that, given a task and a config, produces N programs with full provenance.

### Steps

1. **Task abstraction.** `dpa.task.Task` with fields `prompt`, `entry_point`, `tests`, `reference_solution`, `metadata`. Adapters for HumanEval+, MBPP+, LiveCodeBench so they all flow through the same interface.
2. **Sampler.** `dpa.sampler.LLMSampler` with method `sample(task, n, temperature, paraphrases) -> List[Program]`. Each `Program` carries the full prompt that produced it, the model id, the seed, and the generation params. This provenance is non-negotiable for the rebuttal.
3. **Prompt paraphrase set.** Curate three prompt paraphrases per benchmark task class (function-only prompt, function-with-doctest prompt, function-with-types-emphasis prompt). Distribute samples across paraphrases to broaden the prior support.
4. **Caching.** Hash-key on `(task_id, model_id, prompt_text, temperature, seed)`. A re-run after a downstream bug should hit cache and cost ~$0.
5. **Pre-execution check.** Each sample is run against the canonical doctest; record `passes_doctest: bool`. We do *not* filter on this in the analyzer step — the analyzer runs on all N programs whether they pass or not — but the field is needed for ablations.

### File layout
```
dpa/sampler/
  __init__.py
  llm.py               # LLMSampler
  paraphrases.py       # prompt variant set
  cache.py             # disk-based cache
dpa/task/
  __init__.py
  task.py              # Task dataclass
  humaneval.py         # adapter
  mbpp.py              # adapter
  livecodebench.py     # adapter
```

### Acceptance criteria
- Sampling 20 programs for a HumanEval task finishes in <2 minutes on cached runs (network call only on cache miss).
- Manifest JSON for every run captures git SHA, model id, paraphrase ids, and seed list.

### Risks
- **Output parsing instability.** LLMs don't always emit a clean function. **Mitigation:** robust extractor (regex + AST validation); samples that fail extraction are kept as raw text and tagged `parse_failed: true`. They count toward N but never reach the analyzer. Report parse-failure rate as a metric.

---

## Phase 2 — Analyzer integration (Weeks 2–3, ~8 working days)

**Goal:** a static analyzer that, given a Python function, returns a set of candidate invariants in a normalized, machine-readable form.

### Step 2.1 — Choose the analyzer back-end
Three credible options, in order of preference for a NIER artifact:

1. **CrossHair / Pynguin-style symbolic execution** — produces concrete pre/post-condition predicates by SMT-solving over symbolic inputs. Heavy but precise.
2. **A custom interval + nullability + monotonicity analyzer** — quick to build, easy to interpret, but limited in expressiveness.
3. **Pytype / mypy-style type inference + augmented predicate extraction** — fast, well-supported, but the invariant vocabulary is mostly types (which is weak for the DPA framing).

**Recommendation:** start with option 2 for the pilot (4–5 days to build), upgrade to option 1 for the full evaluation if the pilot is positive. This sequencing buys an early go/no-go without committing to the heavier engineering.

### Step 2.2 — Invariant vocabulary
Define a small, fixed vocabulary so cross-sample comparison is meaningful. Each invariant has a *kind* and a *content*:

```
Kind                 | Content example
---------------------|------------------------------------------------
range                | x: [0, len(xs)]
nullability          | result is not None
length_relation      | len(out) == len(xs) - k + 1
elementwise          | all(out[i] >= min(xs))
monotonicity         | out is non_decreasing
purity               | function does not mutate xs
exception_class      | raises ValueError on k <= 0
postcondition        | out[i] == max(xs[i:i+k])
```

The vocabulary is closed (we add kinds only with strong justification). This is what makes survival a meaningful estimator: invariants must be *commensurable* across samples.

### Step 2.3 — Per-program extraction
For each program, run the analyzer at three program points: function entry, function exit, and each loop head. Return a `Set[Invariant]` per program. Extraction must be deterministic given the same input.

### Step 2.4 — Sandbox
Run the analyzer in a subprocess with CPU and memory limits. Untrusted LLM-generated code can be malicious or simply non-terminating. Use `firejail` or `seccomp`-based isolation; never run samples in-process.

### File layout
```
dpa/analyzer/
  __init__.py
  backend.py           # interface: analyze(program) -> Set[Invariant]
  interval.py          # custom interval/nullability backend (option 2)
  crosshair_adapter.py # heavier backend (option 1)
  sandbox.py           # subprocess + resource limits
dpa/invariants/
  __init__.py
  vocabulary.py        # closed kind set
  invariant.py         # Invariant dataclass + canonical form
```

### Acceptance criteria
- Analyzer extracts ≥3 invariants on average for HumanEval+ tasks.
- Extraction is byte-identical across runs on the same program (determinism check).
- Sandbox kills runaway analyses within 30s.

### Risks
- **Analyzer expressivity ceiling.** The chosen back-end might miss invariants we'd want. **Mitigation:** the vocabulary is the contract; if the back-end can't express a kind, we either drop the kind or upgrade the back-end. The right move depends on which kinds the pilot proves to matter.

---

## Phase 3 — Canonicalization & survival (Week 4, ~5 working days)

**Goal:** turn N per-program invariant sets into a posterior over a unified invariant pool.

### Steps

1. **Canonicalization.** Implement `canonicalize(invariant) -> CanonicalForm` that normalizes:
   - α-rename of bound variables (`x` and `i` should compare equal)
   - constant folding (`len(xs) - k + 1` and `len(xs) - (k - 1)` are the same)
   - commutativity (`a + b == b + a`)
   - logical simplification of conjunctions/disjunctions

   Property test: a small set of hand-picked equivalent invariant pairs must canonicalize to identical strings.
2. **Pooling.** $\mathcal{I}^* = \bigcup_i \mathcal{I}(p_i)$ but over canonical forms.
3. **Survival rate.** $s(\iota) = \frac{1}{N}\sum_i \mathbf{1}[\iota \in \mathcal{I}(p_i)]$. Report per-task and aggregate.
4. **Diagnostics.** For each task, log the number of unique canonical invariants, the survival distribution shape, and the entropy of the prior (used in the Phase 5 prior-collapse analysis).

### File layout
```
dpa/posterior/
  __init__.py
  canonicalize.py
  pool.py              # union over canonical forms
  survival.py          # rate computation + diagnostics
```

### Acceptance criteria
- Canonicalization passes its hand-curated equivalence test set (~30 pairs).
- Survival rates on the smoke-test task are reproducible bit-for-bit across runs.
- Per-task diagnostics file present in every run output.

### Risks
- **Over-aggressive canonicalization** that collapses semantically distinct invariants into one and inflates survival. **Mitigation:** every canonicalization rule comes with a *negative* test asserting that two semantically distinct invariants do *not* collapse.

---

## Phase 4 — Downstream applications (Week 5, ~5 working days)

**Goal:** the three uses of $s(\cdot)$ from §3.3 of the paper, each as a callable with a clean interface.

### Step 4.1 — Sample filtering
- `filter_samples(samples, posterior, threshold) -> List[Program]`: drop samples that violate any $\iota$ with $s(\iota) \geq \tau$. Use $\tau = 0.85$ in the pilot.
- Post-filter, run majority vote on test outputs over the survivors. This is the candidate that goes head-to-head with self-consistency.

### Step 4.2 — Specification refinement
- `refine_spec(prompt, posterior) -> EnrichedPrompt`: surface the top-K survival invariants as candidate pre/post-conditions appended to the prompt.
- For evaluation, this is run as a second sampling pass: take the top-K invariants from the first pass, append to the prompt, sample N more times, re-run pipeline. Measure pass@1 lift.

### Step 4.3 — Disagreement triage
- `triage(posterior, low=0.4, high=0.7) -> List[Disagreement]`: surface mid-range-survival invariants as candidate clarification questions.
- Evaluation is qualitative: on a held-out 30-task sample, do the surfaced disagreements correspond to real spec ambiguities? Hand-rate yes/no.

### File layout
```
dpa/apps/
  __init__.py
  filter.py
  refine.py
  triage.py
```

### Acceptance criterion
On the pilot HumanEval+ set, all three apps run without errors and produce non-empty outputs on >90% of tasks.

### Risks
- **Filtering over-aggression.** If the threshold is too strict, survivors may be empty for some tasks. **Mitigation:** if survivor set is empty, fall back to the unfiltered set and log the event; the experiment still runs.

---

## Phase 5 — Pilot study (Week 6, ~5 working days)

**Goal:** the HumanEval+ pilot reported in the paper. This phase exists to confirm the headline result is real *before* committing to the full evaluation.

### Steps

1. **Reference invariants.** For each of the 164 HumanEval+ tasks, hand-extract a reference invariant set from the canonical solution. Two annotators independently; reconcile disagreements; freeze. **This is the ground truth for Result 1 in the paper and must be done before the experiment to avoid post-hoc fitting.**
2. **Pre-registration.** Commit prompt set, sample budget (N=20), temperature, and the three aggregator definitions (pick-first, self-consistency, DPA-filter) to a git tag *before* running.
3. **Run all conditions.** Three seeds per task per condition. Use a job runner (`make pilot SEED=...`) and write to `runs/pilot/`.
4. **Compute metrics.**
   - **Result 1 (alignment):** Pearson correlation between $s(\iota)$ and binary indicator "$\iota$ in reference set." Plus precision and recall at the $s \geq 0.85$ and $s \leq 0.30$ thresholds.
   - **Result 2 (pass@1):** pass@1 for pick-first, self-consistency, DPA-filter. Bootstrap 95% CIs across seeds.
5. **Qualitative audit.** On the tasks where DPA solves cases self-consistency missed, manually classify whether the survival-flagged invariants captured boundary conventions left ambiguous by the prompt. This is the §4 qualitative claim; do not skip.

### Acceptance criteria
- Result 1: correlation $r \geq 0.6$, otherwise the survival estimator is too noisy and the framing needs rethinking.
- Result 2: DPA-filter beats self-consistency by ≥ 2 absolute points with non-overlapping CIs.

### Decision gate
- If both criteria pass: proceed to Phase 6 confidently.
- If Result 1 passes but Result 2 doesn't: investigate. Likely cause is a weak filtering rule; iterate on threshold and re-run.
- If Result 1 fails: stop and reconsider. The framing depends on survival being informative; if it isn't, we have a no-result paper, which is not a NIER paper.

### Risks
- **HumanEval contamination.** The base model may have memorized solutions, collapsing the prior. **Mitigation:** measure prior entropy per task; if it's near zero on a substantial fraction of tasks, the result is uninterpretable. Backup plan: replicate on LiveCodeBench (which is harder to contaminate) for the headline pilot.

---

## Phase 6 — Full evaluation (Weeks 7–10, ~3 weeks)

**Goal:** answer Q1, Q2, Q3 from §5 of the paper, plus the two open-question controls.

### Q1: Cross-benchmark replication
- **MBPP+** — direct reuse of the Python pipeline; expected to behave like HumanEval+.
- **LiveCodeBench** — harder-to-contaminate benchmark; the most credible replication target. Headline numbers should appear here, not on HumanEval+.
- *Cost estimate:* ~$2k of LLM inference for the closed-model headline, plus open-weight inference time.

### Q2: Model-scale dependence
- Three model classes (frontier closed, strong open-weight, smaller open-weight). Hold prompt, paraphrases, sampling params, and analyzer fixed.
- Hypothesis: smaller models produce noisier samples → more variation for the analyzer to filter → larger DPA lift in absolute terms.
- Reporting: a single plot of (model capability, DPA lift over self-consistency).

### Q3: Beyond functional correctness
- One small case study with a taint-tracking analyzer applied to a security-flavored benchmark (e.g. a curated subset of CWE-tagged tasks). Goal is *demonstration*, not a comprehensive result — appropriate for NIER's "groundbreaking" framing.

### Open-question controls
- **Prior collapse.** Compute prior entropy per task (structural diversity across the N samples). Plot DPA lift as a function of entropy. Hypothesis: lift goes to zero as entropy goes to zero (when all samples are near-copies, survival rates are uninformative). This characterizes the regime where DPA is meaningful versus degenerate.
- **False consensus.** Compare survival rates from a single model family vs. survival rates pooled across heterogeneous models (use 4 distinct model families, 5 samples each instead of 20 from one). Cross-family-surviving invariants are more credible. Report agreement.

### File layout
```
dpa/eval/
  benchmarks/
    humaneval.py
    mbpp.py
    livecodebench.py
  metrics.py           # pass@k, correlation, CIs
  ablations.py         # condition matrix
  controls/
    entropy.py
    cross_family.py
  reports/
    generate_tables.py
    generate_plots.py
```

### Acceptance criteria
- Each benchmark has DPA-filter beating self-consistency at $p < 0.05$ (paired bootstrap test) on at least one model class.
- Entropy plot shows a clean monotonic trend (or, if not, the absence-of-trend is itself a result we report honestly).
- Cross-family agreement plot is generated.

### Risks
- **API cost overrun.** Closed-model inference is the dominant cost. **Mitigation:** budget cap per condition, with cache-then-extend semantics. Apply for academic credits early.
- **Analyzer back-end choice locking us out of an invariant kind that turns out to matter.** **Mitigation:** if the pilot indicates a missing kind, upgrade to the heavier back-end (option 1 in Phase 2.1) before scaling. Reserve Week 7 for this potential upgrade.

---

## Phase 7 — Analysis & writing (Weeks 11–12, ~10 working days)

**Goal:** turn results into a NIER-quality 4-page paper.

### Steps

1. **Quantitative result tables.** Auto-generate from `runs/`. No hand-edited numbers.
2. **Plots.** Three primary figures: (a) survival vs. reference-membership, (b) DPA vs. self-consistency vs. pick-first across benchmarks, (c) lift vs. prior entropy. All generated by scripts in `dpa.eval.reports`.
3. **Worked examples.** Hand-pick three tasks for the paper: one where high-survival invariants matched the reference perfectly, one where mid-survival flagged a real ambiguity (triage application), one where the prior collapsed and DPA was uninformative (honesty).
4. **Threats section honesty.** Document every limitation discovered during execution. Reviewers test whether the authors thought about their own work.
5. **Independent re-coding.** A second annotator blind-re-codes the qualitative audit from Phase 5 step 5. Report Cohen's kappa.
6. **Artifact.** Public anonymous repository with `make reproduce-paper` regenerating every table from cached `runs/`.

### Acceptance criteria
- Submission-ready PDF, 4 pages + 2 references, builds cleanly.
- Anonymous artifact repo with a clear README and a 30-minute reproducibility path on a single task.

---

## Cross-cutting concerns

### Engineering hygiene
- One config file per experiment (`configs/pilot.yaml`, `configs/eval_livecodebench.yaml`). No CLI flags drifting between runs.
- Every run produces `manifest.json`: git SHA, model id, paraphrase set SHA, vocabulary SHA, analyzer back-end commit, dataset SHA. Without these, results are unreproducible.

### Determinism budget
- LLM stochasticity: control via temperature and seed; cache aggressively.
- Analyzer stochasticity: ban it. Determinism is a hard requirement for the back-end choice.
- Canonicalization: deterministic by construction; covered by tests.

### Cost discipline
- Cache LLM completions keyed on `hash(prompt + model + temperature + seed)`. A re-run after a harness bug fix should be near-free.
- Budget-cap closed-model usage at the experiment-config level; refuse to run if projected cost exceeds the cap.

### Failure handling
- Sample fails to parse → tagged, kept in N denominator, never reaches analyzer.
- Analyzer crashes on a sample → sample's invariant set is empty; logged.
- Whole task crashes → re-run once; if it crashes again, drop from the analysis with a logged reason. Reproduction depends on knowing this.

---

## Milestone calendar

| Week | Phase | Deliverable | Pass/fail |
|------|-------|-------------|-----------|
| 0 | Setup | Smoke test green | end-of-week |
| 1 | Sampler | 20-sample HumanEval task end-to-end with cache | end-of-week |
| 2–3 | Analyzer | Invariants extracted on 100 tasks; vocabulary fixed | week 3 review |
| 4 | Posterior | Canonicalization passes equivalence tests; survival reproducible | end-of-week |
| 5 | Apps | Filter / refine / triage runnable on pilot set | end-of-week |
| 6 | Pilot | HumanEval+ pilot, decision gate | **GO/NO-GO** |
| 7–8 | Eval Q1 | MBPP+, LiveCodeBench numbers | week 8 review |
| 9 | Eval Q2 | Model-scale sweep | end-of-week |
| 10 | Eval Q3 + controls | Security case study, entropy plot, cross-family | end-of-week |
| 11 | Analysis | Tables, plots, threats | end-of-week |
| 12 | Writing | Submission-ready PDF + artifact | submission |

---

## What this plan deliberately does *not* do

- **No model fine-tuning.** The whole point of NIER is that DPA works with off-the-shelf samplers. A learned-prior ablation is fair game for the follow-up full paper.
- **No closed-form Bayesian formalism.** The paper uses survival as a frequentist Monte-Carlo estimator. A full probabilistic-programming formalization belongs in the follow-up.
- **No invariant-vocabulary extension mid-experiment.** The vocabulary is frozen after Phase 2. New invariant kinds discovered during analysis are noted but not added — adding them mid-run would re-litigate every survival rate.
- **No multi-language pipeline.** Python only. Java/JS belong in the follow-up.
- **No production tooling.** Research artifact, not a deployable system. No IDE plugin, no CI integration, no service.
- **No deep statistical analysis of the entropy regime.** Phase 6's entropy plot characterizes the regime but does not formalize it. A follow-up paper can.

The discipline of saying "no" to these is what keeps a 12-week project from becoming a 12-month one.

---

## Pilot decision tree (for quick reference)

```
After Phase 5 pilot:

Result 1 (correlation r)
├── r ≥ 0.6                     → continue to Result 2 check
└── r < 0.6                     → STOP. Reconsider survival framing.
                                   Likely cause: vocabulary too coarse
                                   or canonicalization wrong.

Result 2 (DPA vs self-consistency)
├── DPA wins by ≥ 2 points, CIs disjoint  → proceed to Phase 6 confidently
├── DPA wins by < 2 points, CIs overlap   → tune threshold + sample size,
│                                            re-run pilot once
└── DPA loses                              → STOP. The filtering rule
                                            isn't extracting signal even
                                            though it exists. Reconsider
                                            apps (Phase 4).
```

This decision tree is the single most important piece of the plan. It is what prevents three months of effort from arriving at a non-result that could have been called at week 6.
