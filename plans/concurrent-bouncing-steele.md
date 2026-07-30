# Plan: Query-length constraint + 50-item Castform run config

## Context

Accepted questions from the natural-multihop batches are natural-sounding but too long — no real user types 30+ word queries. This change adds a three-layer length regime (prompt guidance ≤20 words, deterministic 25-word cap, word-banded judge rubric) and configures — but does not launch — a 50-item multi-hop run on the Castform (postgres) path. Out of scope: launching the run, LocalRolloutRunner/3b, site-packages edits, hop-count/linker changes.

---

## (i) Where the prompt templates live, and the exact insertion

**Finding:** The multi_hop generation prompt is repo-owned. `NATURAL_MULTIHOP_TEMPLATE` is defined in `run_natural_multihop.py:62-95` and duplicated byte-for-byte in `run_natural_multihop_batch5.py:83-116`, wired via `LLMDirectGenerationConfig.prompt_templates_by_qa_type={"multi_hop": ...}` (`run_natural_multihop_batch5.py:273`). benchmax's built-in default (`generators/direct_llm.py:63 _DEFAULT_TEMPLATE`) is only a fallback and is not used by these runs. Template syntax: `{var}` + `[[if var]]...[[endif]]` (`helpers.py:68`); missing vars are safe (rendered empty, `direct_llm.py:231`).

**The regeneration hint text itself is hard-coded in benchmax** (`pipeline.py:820 _build_regeneration_prompt`; `RefinementConfig.prompt_template` is dead config — no reader). But the feedback surfaces through our template's `[[if regeneration_prompt]]` block, so the constraint is added **inside that block** — repo-owned, no site-packages edit.

**Approach:** The existing scripts are historical records of completed batches — leave them untouched. The new run script `run_multihop_50.py` carries the v2 template (based on the batch5 copy) with these exact edits:

1. Think-step 3 (was "concise (under 35 words)"):
   ```
   3. Verify the question is one sentence of 20 words or fewer, has a single
      coherent intent, and sounds like something typed into a search bar or
      asked of a support agent.
   ```
2. Requirements bullet (replaces "- Keep the question under 35 words. One sentence. No sub-questions joined by 'and'."):
   ```
   - STYLE CONSTRAINT: one sentence, 20 words or fewer, phrased like a real
     customer's search query or support question. No sub-questions joined by
     'and', no stacked qualifiers, no role-play setups ("I'm advising...",
     "Suppose someone...").
   ```
3. Regeneration path — extend the feedback conditional so refined questions don't regrow:
   ```
   [[if regeneration_prompt]]Feedback:
   {regeneration_prompt}

   When rewriting to address this feedback, keep the question to one sentence
   of 20 words or fewer — do not add qualifiers or scenario setup to satisfy
   the feedback.

   [[endif]]
   ```

---

## (ii) Filter-chain pluggability finding: **YES — config-registered via a repo-local factory patch**

Citations (benchmax 0.1.2.dev33, `.venv/.../benchmax/rag/qa_generation/`):

- `FilteringConfig.filters` is `list[str]` (`pipeline_config.py:441-461`); config loading **never validates names** against the supported list (`pipeline_config.py:929-942`) — an unknown name only errors later, inside the factory.
- The chain is built by `_build_filter_chain` (`pipeline.py:367-387`), which calls `_build_filter_from_stage_name` (`pipeline.py:306-364`, a hard-coded if/elif; raises `ValueError` on unknown names at `:361`). **Both are module globals resolved at call time** — the exact monkeypatch seam this repo already uses for `auto_tune` (`run_natural_multihop_batch5.py:228-229`) and plans for `_build_rollout_client` (notes/rollout_interface.md:229-241, sanctioned by CLAUDE.md's wrap-don't-edit rule).
- **Filter order = config list order** (`pipeline.py:373-386`, executed in order at `:1823`). Deterministic guards are a separate always-on stage before the configurable list (`pipeline.py:1596`, `:1810`); putting our name first in `filters` puts it before every LLM filter.
- Filter interface is a duck-typed Protocol, no base class (`protocols.py:41-45`): `evaluate(items: list[GeneratedQA], context) -> list[GeneratedQA]`, setting `item.filter_verdict = FilterVerdict(status=..., reason=..., reasoning=..., metadata=...)` (`generated_qa.py:12-30`). Refinement verdict spelling: `"needs_refinement"`; free-text feedback travels in `metadata["refinement_hint"]` → `_build_regeneration_prompt` (`pipeline.py:835,862-863`) → `{regeneration_prompt}` in our template.
- Verdicts are reset every refinement round (`pipeline.py:1803-1804`), so a regenerated question that is still too long gets re-flagged.
- **Ordering gotcha:** `quality_gate` skips any item whose verdict is non-None (`quality_gate.py:162`, stricter than the other filters). Our filter therefore leaves `filter_verdict = None` on passing items (same convention as deterministic guards) and only sets a verdict on violations.

**Implementation — new file `src/query_length.py`:**

- `HARD_CAP = 25`, `PROMPT_TARGET = 20`, `REFINEMENT_FEEDBACK = "shorten to under 25 words; keep the multi-hop requirement"`.
- `count_words(text) -> int` — `len(text.split())`, same convention as `quality_gate.py:61`.
- `QueryLengthCapFilter`: for each item, skip if `item.filter_verdict is not None and not item.is_passed`; read `str(item.qa.get("question", "")).strip()` (mirrors `quality_gate.py:165`); if `count_words(q) > HARD_CAP`, set:
  ```python
  FilterVerdict(
      status="needs_refinement",
      reason="query_too_long",
      reasoning=f"Question is {n} words; hard cap is {HARD_CAP}.",
      metadata={
          "filter_mode": "query_length_cap",
          "reason_code": "query_too_long",
          "feedback_type": "needs_refinement",
          "refinement_hint": REFINEMENT_FEEDBACK,
      },
  )
  ```
  else leave verdict untouched. Track counts in `context.setdefault("query_length_cap_stats", ...)`.
  (No `failure_type` → normalizes to `unknown` → expected action "address feedback and remain grounded" — correct; we do not want the `too_easy` hop-count bump.)
- `install_query_length_filter()`: wrap `benchmax.rag.qa_generation.pipeline._build_filter_from_stage_name` — return `QueryLengthCapFilter()` for stage `"query_length_cap"`, else delegate to the original. Idempotent (no double-wrap); returns an uninstall handle for tests.
- Stage name `"query_length_cap"` goes **first** in `filtering.filters`. Unknown stage names are harmless to scoring/metrics (`scoring.py:56-61`, `metrics.py:88-95`).

## (iii) Judge prompt diff (conciseness dimension only)

The judge is repo-local, duplicated in both run scripts (`run_natural_multihop.py:98-135` = batch5 `:119-155`); nothing in benchmax. The new script gets rubric **v2**; old scripts stay as-is (their prompts document how prior batches were scored).

```diff
-2. **Conciseness** (0–1): Is it reasonably short? Real users don't write 50+ word questions with embedded clauses.
+2. **Conciseness** (0–1): Score strictly by word count — this question is {word_count} words long:
+   15 words or fewer → 1.0; 16–20 words → 0.9; 21–25 words → 0.7; 26–35 words → 0.4; more than 35 words → 0.1.
```

Dimensions 1, 3, 4 and the response format are unchanged. The judge call passes `word_count=count_words(question)` so the model never miscounts.

**Two deterministic guarantees added in code** (exploration found `overall = min(dims)` is only a prompt instruction today — the code trusts the model's self-reported `overall`, and persisted batch4 scores show violations):
- `conciseness_band(word_count)` in `src/query_length.py` implements the band table; the judge wrapper **overrides** the model's conciseness with the banded value (it is a pure function of word count — nothing is lost).
- The wrapper recomputes `overall = min(single_intent, conciseness, natural_phrasing, plausible_intent)` (falling back to the model's overall only if a dimension is missing). This makes "cutoff 0.6 ⇒ >25 words effectively fails" actually hold (26–35 → 0.4 < 0.6).

Rubric is versioned as `"naturalness_v2_banded_conciseness"` in provenance.

## (iv) Run configuration — `run_multihop_50.py` (configure only, no launch)

New script based on `run_natural_multihop_batch5.py` (config at `:233-305`), output dir `outputs/multihop_50/`. Deltas from batch5:

| Setting | Value | vs batch5 |
|---|---|---|
| `targets.total_samples` | 50 | was 20 |
| type / hop | 100% multi_hop, 100% 2-hop; keep the `auto_tune` stub | same |
| linker | `search_agent`, `search_agent_pct=1.0`, max_turns=4, `fallback_to_metadata=True` | same |
| bundles | `require_bundle("linker_env", backend="postgres")` — **explicit** backend, from `bundles/postgres/` (stamp-verified by `src/bundles.py:37-61`); script prints backend and asserts `SEARCH_BACKEND`, if set, is not `local` | batch5 relied on ambient env var |
| filters | `["query_length_cap", "quality_gate", "retrieval_too_easy_llm", "grounding_llm", "hop_count_validity"]` + `install_query_length_filter()` before `Pipeline(...)` | new first stage |
| generation | gpt-5.4, template **v2** (section i) | v2 |
| refinement | `enabled=True`, `max_refinements_per_item=2` | was 1 — the length cap adds refinement pressure; 1 shared budget would starve the LLM filters. Recorded in provenance. |
| checkpointing | `MicroBatchConfig(resume=True, keep_checkpoints=True, max_parallel_batches=1)` → checkpoints in `outputs/multihop_50/.checkpoints/` (`pipeline_config.py:494-503`); serial batches so the run can be stopped after batch 1 for cost review and resumed | batch5 had `resume=False` (write-only checkpoints) |
| dedup seed | ALL prior questions: `all_scored.jsonl` from `outputs/{natural_multihop, natural_multihop_batch4, natural_multihop_batch5, retrieval_filtered_batch3}` — the pipeline-passed superset of every accepted question, with uniform semantics (batch5's `train/eval.jsonl` were overwritten post-judge, so `all_scored` is the reliable superset). **Missing file ⇒ hard error** (batch5 silently skipped). Same `IncrementalDeduplicator.__init__` pre-seed monkeypatch as batch5 `:204-224`; threshold stays 0.70 bigram-Jaccard default | broader + fail-loud |
| judge | Sonnet (`claude-sonnet-5`), rubric v2, threshold 0.6, keep all above threshold (batch5 behavior) | v2 rubric |

Castform-path notes surfaced in the script banner: requires `PLATFORM_API_KEY`, `LLM_API_KEY`, `ANTHROPIC_API_KEY`; chunk source + retrieval filter hit Castform unconditionally; each item consumes one Castform rollout credit + OpenAI calls (per notes/castform_runbook.md).

**Provenance — `outputs/multihop_50/run_config.json`**, written at config time (before the pipeline runs):
- timestamp, git SHA, `search_backend: "postgres"`, resolved bundle paths + their metadata stamps
- full `PipelineConfig` via `dataclasses.asdict` **with API-key fields redacted**
- `length_constraint`: `{prompt_target_words: 20, hard_cap_words: 25, filter_stage: "query_length_cap", refinement_feedback: "..."}`
- `judge`: `{model, rubric_version: "naturalness_v2_banded_conciseness", threshold: 0.6, bands: {...}, prompt: <full text>}`
- full generation template text, filter list, refinement settings
- `dedup`: prior files + per-file and total question counts

**CLAUDE.md** — one line under "Current migration status":
```
- Batch 6 configured, not launched (run_multihop_50.py → outputs/multihop_50/):
  50 items, Castform path. NEW length regime — ≤20-word prompt target,
  deterministic 25-word cap filter, banded conciseness rubric v2 — results
  not comparable to prior batches.
```

## Tests — `tests/test_query_length.py` (offline, no network)

1. `count_words`: basic whitespace-split cases.
2. Filter behavior: a 24-word question passes through with `filter_verdict` unchanged (stays `None`); a 26-word question gets `status="needs_refinement"` with `metadata["refinement_hint"] == "shorten to under 25 words; keep the multi-hop requirement"` and `reason == "query_too_long"`; items with an existing non-passed verdict are skipped. (`GeneratedQA`/`QADataPoint` construct offline.)
3. Registration: after `install_query_length_filter()`, `_build_filter_from_stage_name("query_length_cap", cfg, source=None)` returns a `QueryLengthCapFilter`; built-ins still resolve (`"quality_gate"`); unknown names still raise `ValueError`; install is idempotent and uninstall restores the original.
4. Ordering: `_build_filter_chain` with `filters=["query_length_cap", "quality_gate"]` returns chain names in that order with our filter at index 0 (i.e. before the LLM filters, which follow in list order).
5. `conciseness_band`: boundary cases 15→1.0, 16→0.9, 20→0.9, 21→0.7, 25→0.7, 26→0.4, 35→0.4, 36→0.1.
6. Judge wrapper (no API): given a fake model response, conciseness is overridden by the band and overall = min of the four dims.

## Files

| File | Change |
|---|---|
| `src/query_length.py` | new — cap filter, factory patch, band function, constants |
| `run_multihop_50.py` | new — 50-item Castform run script (template v2, judge v2, dedup seed, checkpointing, run_config.json) |
| `tests/test_query_length.py` | new — offline tests above |
| `CLAUDE.md` | one status line |
| existing run scripts | untouched (historical record of prior batches) |

## Verification (all offline; run is NOT launched)

1. `pytest` — new tests plus existing suite (castform marker stays deselected).
2. `python -c "import run_multihop_50"`-style smoke is NOT possible (script runs at import); instead a `--dry-run` flag in the script: build config, install the filter patch, resolve postgres bundles, write `run_config.json`, print the banner, and exit before `Pipeline(...)`. Verify with `python run_multihop_50.py --dry-run` — this also exercises `require_bundle("linker_env", backend="postgres")` stamp verification without touching the network.
3. Manually inspect `outputs/multihop_50/run_config.json` for redacted keys and complete provenance.

Launching the run afterwards (not part of this task) is: `python run_multihop_50.py` per notes/castform_runbook.md.
