# Task: generate a RAG eval set with the `benchmax` SDK (castform-ai/benchmax), env_rollout filter enabled

## Context you need
- I already have my chunks. They're **public Chase.com help/product content**, cleared to upload to Castform's hosted corpus.
- I have **$50 Castform credit**. Spend it ONLY on corpus storage, BM25 search, and rollout orchestration — **NOT on LLM tokens**. All LLM calls (generator, judges, the rollout LLM leg) must use **my own** OpenAI/Anthropic key via `base_url`/`api_key`. Never route LLM calls to Castform's LLM proxy.
- Retrieval is **BM25/lexical only** (`PostgresChunkSource`). This is intentional — it matches my production retriever, so the rollout is a conservative answerability oracle. Do NOT switch to hybrid/Turbopuffer/Chroma.
- Rollout orchestration cost per item is **unknown to me**. So we **calibrate on 10 items and STOP** before scaling. This is the most important guardrail: do not run a large batch without showing me calibration numbers first and getting my go-ahead.

## Step 0 — Setup
- Python 3.12 venv. `uv pip install "benchmax[rag]"`.
- Verify benchmax is **pip-installed as a distribution** (NOT a source checkout — the env bundler pickles installed packages by reference; a source checkout pickles by value and fails on a thread lock):
  `python -c "import importlib.metadata as m; print(m.version('benchmax'))"` must print a version.
- Confirm imports:
  `python -c "from benchmax.rag.qa_generation import run_pipeline_from_config; from benchmax.envs.postgres_search.search_env import SearchEnv; from benchmax.bundle import dump_bundle; print('ok')"`

## Step 1 — Credentials (two separate)
- (a) Castform: `castform login` or `PLATFORM_API_KEY`. Show me my **starting credit balance**.
- (b) My LLM key in `.env` as `LLM_API_KEY` / `LLM_BASE_URL`.
- Confirm both resolve before proceeding.

## Step 2 — Upload my chunks
- Inspect my chunk format first and show me a sample BEFORE doing anything.
- Upload via `PostgresChunkSource` (`populate_from_folder` for files, or `populate_from_existing_corpus`/`_name` if already uploaded).
- Do NOT re-upload if a corpus with my name already exists.
- Print the resulting `corpus_id` and chunk count. Run one test BM25 query and show me it returns sensible hits.

## Step 3 — Build the env bundle
- Use `build_env_bundle.py` (I'm providing it). Fill in `CORPUS_NAME` (must match Step 2), `CORPUS_DESCRIPTION`, and `JUDGE_BASE_URL`/`JUDGE_MODEL` (my endpoint).
- Run it; it writes `env_cls.pkl` + `env_metadata.json`.
- If it raises a `_thread.lock` pickling error: benchmax is resolving as a source checkout, not an installed package. Fix the install (Step 0) — do not patch around it.

## Step 4 — Write `config.yaml` (show it to me before running)
Required:
- `corpus`: my `corpus_id` / `corpus_name`.
- Point **every LLM-calling component** at my key — set `base_url`/`api_key` on: `generation.llm_direct`, `refinement`, `filtering.grounding_llm`, `filtering.hop_count_validity` (judge), and `filtering.env_rollout` (both the rollout LLM `api_key`/`base_url` AND `judge_api_key`/`judge_base_url`).
- `filtering.filters`: `["quality_gate","retrieval_too_easy_llm","grounding_llm","hop_count_validity","env_rollout"]`
- `filtering.env_rollout.env_bundle`: `env_cls_file` / `env_metadata_file` → the two files from Step 3.
- `filtering.env_rollout.rollout_limits`: `max_turns: 6`, `max_tool_calls: 8` (NOT the 16/24 default — we're validating, not training; each tool call is a BM25 query).
- `targets.total_samples: 10` for now.
- `targets.hop_distribution`: single-hop-heavy, e.g. `{1: 0.8, 2: 0.2}`. My corpus is self-contained articles; the metadata linker's `filter_same_file=True` means multi-hop will mostly hop-demote, so don't waste refinement budget chasing hops.
- `refinement.max_refinements_per_item: 1` for calibration.
- `output.dir`: a fresh dir. `micro_batch.resume: true`.

## Step 5 — Calibrate on 10 (then STOP)
Run `run_pipeline_from_config("config.yaml")`. Then report:
- (a) Castform credit consumed (balance before vs after).
- (b) My LLM token spend.
- (c) Per-item rollout count + pass/needs_refinement/reject breakdown from `env_filter_stats`.
- (d) Extrapolated cost for 3,000 items.
**Stop here and show me these numbers. Do not proceed to a larger run without my explicit go-ahead.**

## Step 6 — (after my approval) Scale deliberately
Based on calibration, decide with me whether to run env_rollout on all items or only the multi-hop subset (cheapest: run the non-rollout chain on 3,000, then apply env_rollout only where `target_hop_count >= 2`). Bump `total_samples`, resume from checkpoints.

## Notes / gotchas
- The `env_rollout` filter runs ONE full retrieval-agent rollout per candidate on Castform infra, then checks (1) answer matches gold via an equivalence judge and (2) tool-call count >= claimed hop count. "Equivalent but too few tool calls" → `too_easy` → refine. For my BM25-only setup the `too_easy` signal is especially meaningful — it flags questions my real retriever solves trivially.
- Keep the rollout LLM and judge OFF Castform's proxy or the $50 evaporates.
- Don't enable `search_agent` linker (`linker.search_agent_pct: 0.0`) — it adds rollout cost at seeding time too.
