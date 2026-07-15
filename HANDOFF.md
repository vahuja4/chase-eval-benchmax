# Handoff Note — Chase RAG Eval Dataset

## What was done

Built a pipeline that generates QA evaluation pairs from Chase.com help content. The pipeline generates questions, filters them through 5 stages (quality gate, retrieval difficulty, grounding, hop-count validity, agent rollout), and outputs validated QA pairs in JSONL.

### Runs completed

| Run | Target | Passed | Output dir |
|-----|--------|--------|------------|
| Debug (1 sample) | 1 | 1 | `outputs/diag_4_sonnet/` |
| Small calibration | 10 | 9 | `outputs/calibration_10/` |
| Full calibration | 30 | 28 | `outputs/calibration_30/` |

Each output dir contains `train.jsonl`, `eval.jsonl`, and `report.html` (visual report of all QA pairs with scores and reference chunks).

### Key observations from calibration

- **Pass rate**: 93% (28/30), with 24 regeneration attempts
- **Quality**: composite scores 0.842–1.000, grounding 0.97–1.0, retrieval difficulty 1.0 across the board
- **Type skew**: 75% lookup vs 25% multi-hop (target was 34/66). The corpus has low linkability (p50=0.58) so the pipeline auto-reduces multi-hop ratio. Multi-hop items also reject at higher rates.
- **Early stopping**: pipeline hits parse failures on regeneration after exhausting easy seed chunks, stops early around batch 7–8

## Architecture overview

### Pipeline stages (benchmax internals)

1. **Corpus profiling** (stages 1-3) — fetches chunks from platform corpus by `corpus_id`, runs KeyBERT + metadata entity extraction in-memory, builds entity-chunk graph and co-occurrence matrix. Computes a `CorpusProfile` with entity patterns, document frequencies, search capabilities, and a `CorpusMetadataCensus` with linkability percentiles and strata counts.
2. **Linking** — `LinkerConfig(type="metadata")` uses entity co-occurrence from the profile to find chunk pairs/chains that share bridging entities. The linker produces seed chains for multi-hop QA generation.
3. **Generation** — `llm_direct` mode sends seed chunks + linking hints to the generation LLM (GPT-5.4) to produce QA pairs.
4. **Filtering** — 5-stage filter chain: quality gate, retrieval difficulty, grounding, hop-count validity, env rollout.
5. **Refinement** — items that fail filtering get regenerated with feedback (refinement hints, failure reasons). The generator can re-anchor to a different seed chunk after repeated failures on the same one.

### Env rollout filter (the agent loop)

The env rollout filter validates that a QA pair is answerable-but-not-trivial by running a search agent against the corpus:

- **Agent model**: Claude Sonnet 4.6 (configurable)
- **Search env**: `SearchEnv` from benchmax provides a `search` tool (BM25/hybrid over the platform corpus)
- **System prompt** (`SearchEnv.SYSTEM_PROMPT_TEMPLATE`): instructs the agent to reason in `<think>` blocks, break questions into sub-queries, rephrase on miss, and return answers in `<answer>` tags with `[Source: id]` citations
- **Agent loop**: runs server-side in the benchmax rollout service (not in the pip package). Standard tool-use loop: LLM call -> tool selection -> execute search -> feed results back -> repeat. Controlled by `max_turns=6` and `max_tool_calls=8`.
- **Pass criteria**: agent answer must be semantically equivalent to reference (judged by GPT-5.4) AND agent must have used `>= target_hop_count` tool calls. If equivalent but too few tool calls -> "too easy" -> needs refinement. If not equivalent -> needs refinement or reject.
- **Equivalence judge**: `_judge_equivalence()` uses an OpenAI-compatible LLM to compare reference vs candidate answer, returning `(is_equivalent, confidence, reasoning)`.

### Corpus profile logging

`run_pipeline.py` now calls `pipeline.prepare_context()` separately and dumps corpus profile data to `corpus_profile_dump.json` in the output dir before running generation/filtering. This captures:
- Corpus summary and description (LLM-generated)
- Detected search modes and capabilities
- All extracted entities with document frequency, quality score, chunk count
- Top 50 entity co-occurrences (linkage signal)
- Census stats (chunk count, strata, linkability percentiles, header prevalence)

### Data provenance note

The `data/snapshots/chase_2026_05_27/` directory contains artifacts from a **prior corpus preparation pipeline** (entity registry, chain inventory, seed chains, sampling plan, etc.). These are NOT used by benchmax — the benchmax pipeline builds its own entity graph and linking in-memory from the platform corpus. The snapshot files are retained for reference but are independent of the benchmax pipeline.

## Bug fix applied (site-packages)

`_count_tool_calls` in the env rollout filter only counted Anthropic-format tool calls. The rollout service returns OpenAI-format messages. Patched at:

```
/Users/vishal/miniconda3/lib/python3.12/site-packages/benchmax/rag/qa_generation/filters/env_rollout.py
```

Function `_count_tool_calls` (line 46) — added `msg.get("tool_calls")` handling. This patch will be lost on reinstall. Should be reported upstream.

## Current state of run_pipeline.py

- `total_samples=30`, `output=outputs/calibration_30`
- Rollout agent: Claude Sonnet 4.6
- All judges: GPT-5.4
- All LLM calls use user's own API keys (OpenAI + Anthropic)
- Platform API used only for corpus storage, BM25 search, rollout orchestration
- Corpus profile dump added: writes `corpus_profile_dump.json` to output dir before generation

## What to do next

1. **Review the calibration report** — open `outputs/calibration_30/report.html` in a browser
2. **Decide on multi-hop strategy** — if 25% multi-hop is acceptable, proceed; otherwise the corpus would need enrichment or a different linking strategy
3. **Scale up** — change `total_samples` in `run_pipeline.py` to desired count (e.g., 100, 200). Budget constraint: $50 platform credit for corpus/BM25/rollout; LLM costs are on user's own keys
4. **Merge train/eval** — the pipeline splits output 80/20 into train/eval by default, which is unnecessary for a pure eval dataset. Either set `train_ratio=1.0` in config or just concatenate both files
5. **Report the tool-call counting bug** upstream so the site-packages patch isn't needed on reinstall

## Files

| File | Purpose |
|------|---------|
| `run_pipeline.py` | Main runner, all config in Python. Now does prepare_context -> dump profile -> run_from_context |
| `build_env_bundle.py` | Builds env bundle for rollout filter (already done) |
| `env_cls.pkl` / `env_metadata.json` | Env bundle files used by rollout filter |
| `pipeline_writeup.md` | Full technical writeup of the pipeline |
| `.env` | API keys (LLM_API_KEY, ANTHROPIC_API_KEY, PLATFORM_API_KEY, LLM_BASE_URL, LLM_MODEL) |
| `outputs/*/report.html` | Visual reports for each run |
| `outputs/*/corpus_profile_dump.json` | Corpus profile snapshot (entities, co-occurrences, census) — new |
| `data/snapshots/chase_2026_05_27/` | Legacy corpus prep artifacts (not used by benchmax) |

## Key benchmax source files (in site-packages)

| File | What it does |
|------|--------------|
| `benchmax/rag/qa_generation/pipeline.py` | Main pipeline orchestration — stages 1-6, context prep, batch loop, refinement |
| `benchmax/rag/qa_generation/corpus_profile.py` | `CorpusProfile` class, KeyBERT entity extraction, census computation |
| `benchmax/rag/qa_generation/filters/env_rollout.py` | `EnvRolloutFilter` — runs agent rollout, judges equivalence, decides pass/refine/reject |
| `benchmax/envs/postgres_search/search_env.py` | `SearchEnv` — defines the agent's system prompt and search tool schema |
| `benchmax/platform/client.py` | `RolloutClient` — sends rollout requests to platform, streams SSE events |

## Known issues

1. **Env rollout rewards all 0.0** — SearchEnv judge returns 401 from rollout service. Doesn't affect pipeline (filter uses its own judge function).
2. **Parse failures on regeneration** — generation LLM occasionally returns malformed JSON, causing early stopping after 5 consecutive failures.
3. **Calibration report footer** — `passed_count`/`rejected_count` fields don't populate from `pipeline.run()` return dict.
