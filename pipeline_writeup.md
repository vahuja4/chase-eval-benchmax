# Chase RAG Evaluation Dataset: QA Generation Pipeline

## Overview

This project generates a retrieval-augmented generation (RAG) evaluation dataset from Chase.com public help content. The pipeline produces question-answer pairs that are grounded in a chunked corpus, filtered for quality and difficulty, and validated via agent rollouts.

The goal: produce QA pairs that are hard enough to require non-trivial retrieval (not solvable by naive keyword matching), fully grounded in the source material, and verified by an agent that must actually search and find the answer.

## Pipeline Architecture

The pipeline runs in 6 stages:

```
[1] Load Corpus        Fetch and index 3,089 chunks from Chase help articles
         |
[2] Build Profile      Sample chunks, summarize corpus, extract entity patterns
         |
[3] Entity Extraction  KeyBERT-based entity extraction + co-occurrence graph
         |
[4] Prepare Generation Set up linker, generator, filters, task queue
         |
[5] Work Queue         Micro-batched generate → filter → refine loop
         |
[6] Format Output      Score, deduplicate, balance types, write JSONL
```

## Stage 1-3: Corpus Loading & Profiling

The pipeline loads chunks from the pre-built Chase corpus (3,089 chunks across 289 documents). It then:

- Samples diverse chunks and builds a **corpus profile** summarizing what the corpus covers
- Extracts **discriminative entities** using KeyBERT (proper nouns, product names, financial terms)
- Builds an **entity-chunk index** and **co-occurrence graph** to support chunk linking

The corpus profile is used later to give the generation LLM context about what kinds of questions are appropriate.

Key corpus stats for this project:
- 3,089 chunks, 289 files
- Chunk sizes: 54-2,177 chars (mean: 505)
- Low linkability (suitability p50=0.58) — this limits multi-hop generation
- 0% date metadata — temporal reasoning disabled

## Stage 4: Task Preparation

The pipeline computes a batch of **generation tasks** based on target distributions:

| Parameter | Value | Notes |
|-----------|-------|-------|
| Total samples | 30 | Calibration batch |
| Lookup | 34% | Single-chunk questions |
| Multi-hop | 66% (reduced to ~30%) | Multi-chunk reasoning; reduced due to low corpus linkability |
| Hop distribution | 1-hop: 34%, 2-hop: 33%, 3-hop: 33% | For multi-hop items |

Each task specifies:
- A **seed chunk** (randomly sampled, filtering out bottom-quartile poor chunks)
- A **qa_type** (lookup or multi_hop)
- A **target hop count** (how many chunks the answer should require)
- A **reasoning mode** (factual, temporal, inference, sequential)

## Stage 5: The Generate-Filter-Refine Loop

This is the core of the pipeline. It runs in micro-batches with checkpointing.

### 5a. Chunk Linking

Before generating a question, the pipeline finds **secondary chunks** that relate to the seed chunk. This is what makes multi-hop questions possible.

The **metadata linker** (used in this project) works as follows:

1. Extract queries from the seed chunk's metadata (headings, titles, entities)
2. Search the corpus for related chunks using BM25
3. Filter candidates: remove same-file chunks, duplicates, chunks already used
4. Score candidates by a composite of search relevance (40%), Jaccard similarity (30%), and entity overlap (30%)
5. Enforce diversity: skip candidates too similar to the primary (>0.55 Jaccard) or to each other
6. If confidence is low (few secondaries found), retry with content-derived queries

Output: an **AnchorBundle** containing the primary chunk + up to 3 secondary chunks + linking confidence.

### 5b. QA Generation

The **DirectLLMGenerator** sends the linked chunks to an LLM (GPT-5.4 in this project) with instructions to generate a question-answer pair. The prompt includes:

- Corpus context (what Chase.com help articles cover)
- The primary chunk content
- Secondary chunks (for multi-hop questions)
- The target qa_type and reasoning mode
- For regeneration attempts: the previous failure analysis and expected fix

The LLM returns structured JSON with: question, answer, reasoning, and reference_chunk mappings.

### 5c. Filter Chain

Every generated QA pair passes through 5 filters in sequence. If any filter fails, the item is either rejected or sent back for regeneration.

#### Filter 1: Quality Gate (deterministic)

Fast heuristic checks before expensive LLM calls:

- **Fragment detection**: rejects keyword-only questions lacking verbs or interrogatives
- **Structural rejection**: rejects questions about page layout, table of contents, etc.
- **Guide pointer rejection**: rejects "where can I find..." / "check out the docs" patterns
- **Thin answer detection**: flags answers that are too short relative to the question

#### Filter 2: Retrieval Difficulty (LLM judge)

Ensures the question isn't trivially solvable by BM25 keyword matching. Two-phase approach:

1. **Overlap pre-gate** (deterministic): search the corpus with the question text. If the reference chunks appear in the top-k BM25 results with >65% overlap, auto-reject as "too_easy"
2. **LLM judge**: for items that pass the pre-gate, a GPT-5.4 judge evaluates whether naive lexical retrieval would find the answer

Rejection reason: `too_easy` — the question uses the same keywords as the source, making retrieval trivial.

#### Filter 3: Grounding (LLM judge)

Verifies the answer is fully supported by the reference chunks:

- A GPT-5.4 judge receives the question, answer, and chunk evidence
- Returns: answerable (bool), confidence, supporting_chunk_ids
- If unsupported: triggers reanchoring (try a completely different seed chunk)
- If partially supported: prunes reference_chunks to only the supported ones

Rejection reason: `unsupported` — the answer contains claims not found in the chunks.

#### Filter 4: Hop-Count Validity (LLM judge)

For multi-hop questions only. Uses **leave-one-out testing**:

- For each reference chunk, remove it and ask the judge if the answer is still derivable
- If all chunks are independently sufficient, the question isn't truly multi-hop
- Computes a difficulty_score based on how many chunks are essential

Rejection reason: `lopsided` — removing any single chunk still allows answering (not genuinely multi-hop).

#### Filter 5: Env Rollout (agent execution)

The most rigorous filter. An actual agent (Claude Sonnet 4.6) attempts to answer the question using a search tool:

1. The agent receives the question and a BM25 search tool over the Chase corpus
2. It searches iteratively (up to 8 tool calls, 6 turns, 120s timeout)
3. Its final answer is extracted from `<answer>...</answer>` tags
4. A GPT-5.4 judge compares the agent's answer to the reference answer

Verdict logic:
- Agent's answer matches reference AND used enough tool calls → **passed**
- Agent's answer matches but too few tool calls → **too_easy** (agent found it too quickly)
- Agent's answer doesn't match → **incorrect** (question may be ambiguous or too hard)

Configuration in this project:
| Parameter | Value |
|-----------|-------|
| Rollout model | claude-sonnet-4-6 |
| Judge model | gpt-5.4 |
| Max turns | 6 |
| Max tool calls | 8 |
| Max tokens | 2,048 |
| Timeout | 120s |

Note: the env rollout rewards (answer_correctness, citation_precision, etc.) are all 0.0 due to a separate 401 auth issue with the SearchEnv judge. This doesn't affect the pipeline — the env_rollout filter uses its own `_judge_equivalence` function, not the env's reward signal.

### 5d. Refinement / Regeneration

When a filter returns `needs_refinement` instead of `rejected`, the item gets another chance:

1. The failure analysis is packaged into a **regeneration prompt** that tells the LLM what went wrong
2. Based on failure_type, the expected action varies:
   - `too_easy` → increase difficulty while keeping the answer factually locked
   - `unsupported` → reanchor to new evidence and revise the answer
   - `lopsided` → restructure to genuinely require all reference chunks
3. If the same seed chunk fails 2+ times, the pipeline **reanchors** to a completely different seed chunk
4. Regenerated items go through the full filter chain again
5. Up to 4 rounds of refinement per batch

Early stopping triggers if:
- 5 consecutive batches produce 0 accepted items
- Repeated parse failures on regeneration (LLM returns malformed JSON)

## Stage 6: Scoring, Deduplication & Output

### Composite Scoring

Each passing item receives a composite score:

```
composite = 0.4 * grounding + 0.3 * retrieval_difficulty + 0.3 * hop_validity
```

Items are sorted by composite score so the highest-quality ones fill type quotas first.

### Type Balancing

The pipeline enforces the target type distribution:
- If an item labeled "multi_hop" has all reference chunks from the same file, it's relabeled to "lookup"
- Items are accepted greedily by composite score until each type's quota is filled
- Excess items are rejected with `type_quota_exceeded`

### Train/Eval Split

The pipeline splits output into train.jsonl and eval.jsonl using stratified sampling (default 80/20 split by qa_type). For pure evaluation dataset generation, this split is unnecessary — all items are valid QA pairs.

### Output Schema

Each item in the JSONL files:

```json
{
  "question": "natural language question",
  "answer": "reference answer grounded in chunks",
  "qa_type": "lookup | multi_hop",
  "reference_chunks": [
    {
      "id": "chunk_hash",
      "content": "full chunk text",
      "metadata": {
        "file": "p_00136",
        "stratum": "education_center",
        "chunk_id": "c_00136_09",
        "page_title": "How to Increase Your Approval Odds for a Credit Card | Chase",
        "sub_stratum": "basics",
        "heading_path": "How to boost your credit card approval odds > What information..."
      }
    }
  ],
  "eval_scores": {
    "grounding": 0.97,
    "retrieval_difficulty": 1.0,
    "composite": 0.994,
    "query_style_observed": "natural"
  },
  "linking_hints": {
    "linker": "metadata",
    "confidence": 0.0
  }
}
```

## Calibration Results (30-sample run)

| Metric | Value |
|--------|-------|
| Passed | 28 |
| Rejected | 9 |
| Regenerations | 24 |
| Pass rate | 93% (of target) |
| Lookup | 21 (75%) |
| Multi-hop | 7 (25%) |
| Composite score range | 0.842 - 1.000 |
| Runtime | ~15 minutes |

The multi-hop ratio undershot the 66% target (achieved 25%) because:
1. The corpus has low linkability (suitability p50=0.58), causing the pipeline to auto-reduce the multi-hop ratio to ~30%
2. Multi-hop items have higher filter rejection rates (harder to ground across multiple chunks)

## Known Issues

1. **Tool call counting patch**: `_count_tool_calls` in the env rollout filter was patched to handle OpenAI-format tool calls (`msg["tool_calls"]`) in addition to Anthropic-format (`msg["content"]` blocks with `type: "tool_use"`). This is a local edit that will be lost on reinstall.

2. **Env rollout rewards all 0.0**: The SearchEnv judge returns 401 from the rollout service. This doesn't affect filtering (the env_rollout filter uses its own judge), but means the reward signal in the logs is meaningless.

3. **Parse failures on regeneration**: The generation LLM occasionally returns malformed JSON during regeneration, causing `failed to parse QA response` errors. After 5 consecutive failures, the pipeline stops early.

4. **Calibration report fields empty**: The `result` dict from `pipeline.run()` doesn't populate `passed_count`/`rejected_count` — minor reporting issue.

## Configuration Reference

The full pipeline config is in `run_pipeline.py`. Key settings:

| Setting | Value | Purpose |
|---------|-------|---------|
| `corpus` | Chase help articles | Chase help corpus |
| `total_samples` | 30 | Calibration batch size |
| `linker.type` | `metadata` | Zero-cost chunk linking |
| `generation.mode` | `llm_direct` | Direct LLM generation |
| `filters` | quality_gate, retrieval_too_easy_llm, grounding_llm, hop_count_validity, env_rollout | Full filter chain |
| `env_rollout.model` | `claude-sonnet-4-6` | Rollout agent model |
| `*_judge_model` | `gpt-5.4` | All judge calls |
| `refinement.max_refinements_per_item` | 1 | One retry per failed item |
| `micro_batch.resume` | true | Resume from checkpoints |

All LLM calls use the user's own OpenAI/Anthropic API keys. The platform API is used only for corpus storage, BM25 search, and rollout orchestration.
