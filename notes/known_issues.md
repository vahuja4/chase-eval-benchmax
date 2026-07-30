# Known Issues

## 1. `_count_tool_calls` patch (site-packages)

`_count_tool_calls` in the env rollout filter only counted Anthropic-format tool calls (`tool_use` content blocks). The rollout service returns OpenAI-format messages, so tool calls were never counted — causing the "too few tool calls" check to misfire.

**Patched at:**
```
/Users/vishal/miniconda3/lib/python3.12/site-packages/benchmax/rag/qa_generation/filters/env_rollout.py
```

**What changed:** added `msg.get("tool_calls")` handling in `_count_tool_calls` (line 46) so it recognises both Anthropic and OpenAI message formats.

**Risk:** this patch lives in site-packages and will be lost on reinstall or upgrade. Should be reported upstream.

## 2. Malformed-JSON early stopping on regeneration

The generation LLM occasionally returns malformed JSON during regeneration rounds. After 5 consecutive parse failures the pipeline treats the batch as exhausted and stops early (typically around batch 7–8 in a 30-sample run).

This tends to happen after the pipeline has already used the easier seed chunks and is regenerating from harder ones — the LLM struggles more with the remaining material and produces structurally invalid output more often.

## 3. `RefinementConfig.prompt_template` is dead config

`RefinementConfig.prompt_template` (with its `feedback={feedback}` placeholder, `pipeline_config.py:475-480`) is parsed from YAML (`pipeline_config.py:1058-1059`) but has **no reader anywhere in benchmax** — the refinement path goes through the generator's `prompt_templates_by_qa_type` template instead. Setting it has no effect. Filter feedback must travel via `FilterVerdict.metadata["refinement_hint"]`, which `_build_regeneration_prompt` (`pipeline.py:835,862-863`) renders into `{regeneration_prompt}`.

## 4. Naturalness judge `overall = min(dims)` was prompt-only in batches 1–5

The judge prompt instructs the model to report `overall` as the minimum of the four dimension scores, but the run scripts for batches 1–5 trusted the model's self-reported `overall` without recomputing it. Persisted batch4 scores (`outputs/natural_multihop_batch4/step_5_naturalness_scores.json`) contain rows where `overall > min(dims)` — i.e. some accepted questions would have failed under a code-enforced min.

**Provenance caveat:** prior batches' naturalness verdicts are not strictly min-of-dimensions. Candidate follow-up: retroactively re-score prior batches with the banded wrapper (`src/query_length.py::apply_banded_scores`), which enforces both the conciseness band and the min rule in code. Batch 6 (`run_multihop_50.py`) onward uses the enforced version.

## 5. Unpinned `benchmax` in env bundles breaks Castform rollouts (discovered 2026-07-30)

Bundles built with `pip_dependencies=["benchmax"]` became uninstallable on Castform rollout workers: PyPI's stable benchmax releases (0.2.0, 0.2.1) were yanked ("not public yet"), leaving only pre-releases, which the worker's resolver refuses without an explicit pre-release pin. Every rollout then dies at env install ("Failed to install pip dependencies … all versions of benchmax were yanked"), the linker silently produces single-chunk bundles, and **no multi-hop item can ever pass** — the first batch-6 pilot burned 68 minutes at 0/10 accepted with 106 failed rollout attempts before being killed (`outputs/multihop_50/run_log_attempt1_bundle_deps.txt`).

**Fix:** `build_env_bundle.py` now pins the exact installed version (`benchmax==0.1.2.dev33` via `importlib.metadata.version`); postgres bundles rebuilt 2026-07-30 with the pin stamped in metadata.

**Detection gaps:** (a) `pytest -m castform` health check only exercises BM25 search, not the rollout path, so this passed while rollouts were broken; (b) the pipeline treats both rollout failure (metadata-linker fallback) and corpus-profiling failure (static-description fallback) as non-fatal, so a fully broken dependency degrades quietly instead of aborting — watch the run log for "Failed to install pip dependencies" and for rejected items with exactly one reference chunk.

## 6. Linker can't parse OpenAI-format tool calls from Castform workers (discovered 2026-07-30)

After fixing #5, rollouts succeeded but every anchor bundle still came back empty: Castform workers return OpenAI-format assistant messages (`content=""` + `tool_calls[].function.arguments` as a JSON string), and the installed benchmax `_extract_queries` (`search_agent_linker.py`) only parses Anthropic `tool_use` content blocks and Hermes `<tool_call>` XML. No queries extracted → `no_queries` empty bundle → single-chunk items → post-processing relabels them `lookup` → type-quota balancer rejects everything (quota is 100% multi_hop). Batch-6 pilot attempt 2 rejected 5/5 this way (`outputs/multihop_50/run_log_attempt2_toolcall_format.txt`). Same format-mismatch family as #1. Diagnosed with `debug_rollout_messages.py`.

**Fix:** repo-local monkeypatch `src/rollout_compat.py::install_openai_toolcall_extraction()` extends `_extract_queries` with OpenAI `tool_calls` parsing (installed by `run_multihop_50.py`; site-packages untouched). Tests: `tests/test_rollout_compat.py`.

**Twist that hid the bug:** this machine has TWO benchmax installs both reporting 0.1.2.dev33 — miniconda's (the one `python` actually runs, missing the OpenAI branch) and `.venv`'s (which already contains it, suggesting upstream fixed this in a same-versioned rebuild). Any "does benchmax handle X?" check must be run against the interpreter that executes the pipeline, i.e. `python -c "import benchmax; ..."`, not against whichever site-packages a file search happens to find.

**Why batch5 (2026-07-17) worked:** before the PyPI yank (#5), unpinned bundles installed a stable 0.2.x benchmax on the worker, whose env emitted Hermes `<tool_call>` XML that the local dev33 linker could parse. The yank forced the pin to dev33 on the worker, whose tool-calling is OpenAI-native — exposing this local parsing gap.
