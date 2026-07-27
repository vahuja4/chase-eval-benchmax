# Eval Generation Pipeline — Reference

> **Provenance:** Converted from `outputs/natural_multihop/pipeline-explainer.html`
> (generated during the natural multi-hop runs). This supersedes
> `pipeline_writeup.md`, which describes the earlier metadata-linker /
> env_rollout configuration. Values marked **[example run config]** describe the
> specific run this explainer was generated from — they are illustrative, not
> requirements.

A multi-stage system for generating high-quality question–answer pairs from
document corpora, with LLM-powered linking, iterative filtering, and automated
regeneration.

The pipeline ingests a corpus of document chunks and produces evaluated QA
pairs suitable for training and benchmarking RAG systems. It handles the full
lifecycle: profiling the corpus to understand its structure, linking chunks
that share cross-document relationships, generating questions via LLM,
validating each question through a chain of automated judges, and regenerating
any that fail validation with targeted feedback.

- **Output:** QA pairs (multi-hop and lookup types), train/eval split
- **Strategy:** generate & filter, with a regeneration loop for failed items
- **Execution:** micro-batched, dynamically sized, checkpointed, resumable

## Architecture at a glance

```
Corpus Loading
   → Corpus Profiling & Entity Extraction
   → Chunk Linking
   → QA Generation
   → Filter Chain:
        Deterministic Guards
        Quality Gate
        Retrieval Too Easy
        Grounding LLM
        Hop Count Validity
        (failed items → Refinement → regenerate → re-filter)
   → Post-Processing & Dedup
   → Train / Eval Split
   → Naturalness Judge (Claude Sonnet)
```

---

## Phase 1 — Preparation

### Corpus loading

The pipeline starts by loading document chunks from the corpus. Chunks are the
atomic units of text — paragraphs or sections of documents, each identified by
a unique hash with associated metadata (file path, headers, document ID). In
this project the corpus is the Chase.com public help articles (credit cards,
banking, auto loans, mortgages), crawled and chunked in a prior step.

A diverse profile sample is drawn from the full corpus. This sample drives
corpus profiling, entity extraction, and seed chunk selection for generation.
The sampling strategy prioritizes diversity across documents rather than
random draws, ensuring coverage of different topics and document types.

### Corpus profiling

An LLM generates a structured summary of what the corpus contains, along with
representative example queries. The profiler receives sampled top-level chunks
(document beginnings) and random deep chunks, combined with any user-provided
description.

This corpus summary is injected into every generation prompt, giving the
question-writing LLM context about the domain, vocabulary, and types of
information available. Without profiling, the generator would work blind.

### Entity extraction

When enabled, the pipeline extracts named entities and key phrases from all
corpus chunks using KeyBERT combined with metadata analysis. This builds three
structures:

- **Entity → Chunk index** — which chunks mention each entity
- **Chunk → Entity index** — which entities appear in each chunk
- **Entity co-occurrence matrix** — which entities appear together, enabling
  cross-document relationship discovery

These indices feed into the linker and the auto-tuner, helping the pipeline
understand which chunks can be meaningfully connected for multi-hop questions.

### Auto-tuning

After profiling, the pipeline checks whether the requested settings are
realistic for this particular corpus, and dials them back if not:

- **Multi-hop percentage** — if the corpus has weak cross-document connections
  (unstructured metadata, few shared entities), the pipeline lowers the share
  of multi-hop questions so it isn't forced to fabricate thin connections.
- **Hop count** — if most chunks are short or few are suitable for linking,
  3+-hop questions are cut back in favor of 2-hop, since there isn't enough
  material to chain three or more chunks reliably.
- **Total sample count** — if more questions are requested than the corpus can
  support (e.g. 500 questions from 100 usable chunks), the count is capped at
  twice the usable pool.
- **Reasoning modes** — modes like "temporal" (date-based reasoning) or
  "sequential" (step-order reasoning) are removed or reduced if the corpus
  lacks the relevant metadata (e.g. fewer than 5% of chunks have dates).

---

## Phase 2 — Linking & Generation

### Chunk linking

For each generation task, the linker finds a **primary chunk** (the seed) and
one or more **secondary chunks** that share a meaningful relationship.
Together, these form an **anchor bundle** — the evidence base from which a
multi-hop question will be generated.

Three linking strategies are available, selectable via configuration:

| Linker | How it works | Best for |
|---|---|---|
| **Metadata** | Finds secondary chunks by structural signals: same document, shared headers, overlapping entities, metadata similarity. Fast and deterministic. | Corpora with rich metadata and clear document structure |
| **Search Agent** | An LLM-powered agent with access to corpus search tools. It reads the primary chunk, formulates search queries, evaluates results, and iteratively discovers connections — mimicking how a human researcher would find related content. Uses rollout-based exploration with configurable turn and tool-call limits. | Finding deep semantic connections across documents |
| **Wiki** | Uses pre-built entity cluster wiki pages (generated from the entity co-occurrence graph) to find chunks connected through shared topic clusters. | Entity-dense corpora with clear topic clusters |

### Search agent linker internals

Every linking request starts with a **fast, non-LLM pass** that builds search
queries from the primary chunk's own structure — its headings (h1/h2/h3),
named entities found in the text, and TF-IDF keyphrases — then runs those
queries against the corpus search index to find candidate secondaries. This
first pass is cheap (no LLM calls) and produces a confidence score based on
how many good candidates it found.

The linker then decides whether to **upgrade to the LLM-driven approach**
based on two triggers:

1. The fast pass found weak results (confidence below 0.5), or
2. The task is randomly selected by `search_agent_pct` (e.g. `1.0` = always
   use the LLM path)

When the LLM path fires, an LLM is given the primary chunk's content and asked
to find related chunks that could support a multi-hop question. The LLM can
call corpus search tools (semantic, keyword, and hybrid) — it reads the
primary chunk, decides what to search for, reviews the results, and refines
its queries. This runs as an agentic loop, typically over 3–4 turns, with
configurable limits on turns and tool calls.

The rollout captures all of the agent's messages, tool calls, and reasoning.
From these, the linker extracts two things:

- **Search queries** — parsed from the agent's tool calls (supports Anthropic
  `tool_use` blocks, OpenAI-style function calls, and XML `<tool_call>` tags)
- **Evidence chain** — the agent's explanation of how the chunks connect,
  parsed from `<evidence_chain>` tags in its final message

The extracted queries are then **replayed against the actual corpus search
index** to retrieve real Chunk objects. These candidates go through a
multi-step filter:

1. Chunks shorter than 400 characters are dropped
2. Same-file chunks are excluded (unless in "sequential" reasoning mode)
3. Chunks already used by prior questions are skipped (cross-question dedup)
4. A Jaccard coherence floor (≥ 0.15 token overlap with the primary) removes
   unrelated results

Surviving candidates are ranked by a composite score (60% search relevance,
40% coherence), then passed through a greedy diversity selector that caps
pairwise similarity at 0.8 to avoid near-duplicate secondaries. The top N
become the anchor bundle's secondary chunks.

If the LLM rollout fails for any reason, the linker **falls back to the
metadata linker's** result (flagged with `llm_fallback: true`).

### QA generation

Given an anchor bundle, an LLM generates a question–answer pair. The
generation prompt includes the corpus summary, primary and secondary chunk
content, structural hints from the linker (e.g. evidence chains explaining how
chunks relate), and — for regeneration attempts — feedback from previous
filter failures.

The pipeline doesn't generate all questions at once — it works in small
batches (e.g. 5 at a time), running each batch in parallel. Before each batch,
it checks how many questions of each type it still needs and assigns work
accordingly.

For every question, the pipeline decides three things up front:

- **Question type** — lookup (answerable from a single article) or multi-hop
  (requires combining information from multiple articles)
- **Hop count** — for multi-hop questions, how many articles the reader needs
  to consult (e.g. 2-hop = combining two articles)
- **Starting article** — which chunk to use as the seed; the linker then
  finds related chunks to pair with it

The mix is controlled by config. **[example run config]** In the
natural-multihop run, 100% of questions were multi-hop and all targeted 2-hop.

### Custom prompt templates

Each `qa_type` can have its own prompt template. Templates use a simple
placeholder syntax (`{variable_name}`) and conditional blocks
(`[[if var]]...[[endif]]`). Available variables include:

- `{corpus_summary}` — the profiled corpus description
- `{primary_chunk}`, `{secondary_chunks}` — chunk content
- `{evidence_chain}` — how chunks connect (from the linker)
- `{target_hop_count}` — desired reasoning depth
- `{failed_question}`, `{regeneration_prompt}` — feedback for retries

---

## Phase 3 — Validation

### Filter chain

Every generated QA pair passes through a configurable sequence of filters.
Each filter sets one of three verdicts: **passed** (accepted), **rejected**
(permanently dropped), or **needs refinement** (sent to regeneration). The
chain is ordered — a question must survive each stage to reach the next.

1. **Deterministic Guards** — format validation, length checks, structural
   requirements. No LLM calls; pure rule-based.
2. **Quality Gate** — basic quality checks: is it a well-formed question?
   Does the answer make sense? Rejects malformed or trivial outputs.
3. **Retrieval Too Easy** — checks whether a simple keyword search would
   already find the answer. Two layers: first, the corpus is searched using
   the question text and the overlap between returned results and the
   question's reference chunks is measured; high overlap → immediately
   flagged too easy. Otherwise an LLM judge reviews the search results and
   decides whether the question could be answered from them alone.
   **[example run config]** In batch3, this filter rejected 10 of 22
   generated questions.
4. **Grounding LLM** — an LLM judge verifies the answer is actually supported
   by the referenced chunks. Catches hallucinated or extrapolated answers.
5. **Hop Count Validity** — an LLM judge verifies the question genuinely
   requires the claimed number of reasoning hops. Catches questions that look
   multi-hop but can be answered from a single chunk.

> **Note:** the earlier calibration configuration also included an
> `env_rollout` filter (a search agent attempting the question end-to-end).
> It is not part of the natural-multihop runs this document describes; see
> `pipeline_writeup.md` (archived) for its design.

### Regeneration loop

Items with a `needs_refinement` verdict are sent back to the generator with
specific feedback about why they failed, forming a closed loop:
generate → filter → feedback → regenerate → re-filter. The loop runs up to
`max_rounds` times per batch. Each regeneration prompt includes:

- The failure reason and judge reasoning from the previous attempt
- The previous question and answer to improve upon
- A failure type classification (`too_easy`, `unsupported`, `unknown`) that
  determines the expected corrective action
- A refinement hint with specific guidance

**Failure type → expected action:**

| Failure type | Expected action |
|---|---|
| `too_easy` | Increase difficulty while keeping the answer locked to the source chunks |
| `unsupported` | Reanchor to new evidence and revise the answer using the new chunks |
| `unknown` | Address the filter feedback while remaining grounded in source evidence |

### Seed reanchoring

If a question fails repeatedly with the same seed chunk, the pipeline can
**reanchor** — switch to a different seed chunk entirely — preventing wasted
regeneration rounds on a chunk that can't support a good question. The
threshold is configurable (`max_same_seed_attempts_before_reanchor`). When
reanchoring, the pipeline first tries to sample a fresh chunk from the corpus;
if that fails, it rotates to another chunk from the existing seed pool.

---

## Phase 4 — Output

### Post-processing

After all batches complete and filtering/regeneration converges, global
post-processing runs on the full accepted set:

- **Deduplication** — removes near-duplicate questions using n-gram
  similarity (configurable threshold), preventing rephrased versions of the
  same question.
- **Type relabeling** — corrects `qa_type` labels based on actual reference
  chunk structure. A question labeled `multi_hop` with all chunks from the
  same document is relabeled `lookup`, and vice versa.
- **Type quota balancing** — accepts items up to the target count per
  `qa_type`, sorted by composite quality score. Excess items beyond the quota
  are rejected even if they passed all filters.

### Train / eval split

Final accepted items are split into training and evaluation sets, stratified
by `qa_type` and style so both sets have representative distributions. Default
ratio: 80% train / 20% eval.

Each output item includes: question, answer, reference chunks, eval scores
(grounding, hop validity, composite), generation metadata, and the full
**journey event log** tracking every stage the item passed through.

---

## Phase 5 — Naturalness Judge

After the pipeline finishes, every question that passed the filter chain goes
through one more check: does it sound like something a real person would
actually ask?

The pipeline uses GPT for generation and grounding; this step deliberately
uses a **different model family (Claude Sonnet)** to judge naturalness. A
cross-model judge catches patterns the generator considers normal but a fresh
reader finds awkward or manufactured.

Each question is scored 0.0–1.0 on four dimensions:

| Dimension | What it checks | What gets flagged |
|---|---|---|
| **Single Intent** | Is the question asking one clear thing? | Stitched-together unrelated questions ("What's the APR and also how do points transfers work?") |
| **Conciseness** | Is it a reasonable length? | Long questions with nested clauses and qualifiers |
| **Natural Phrasing** | Would you type it into a search bar or ask a support agent? | Role-playing ("I'm advising a first-time borrower who..."), manufactured setups |
| **Plausible Intent** | Would a real person actually want to know this? | Questions that exist only to connect unrelated topics |

The overall score is the **minimum** of the four — one bad dimension fails the
whole question. Any question scoring below **0.6** is dropped. This is
typically the strictest filter in the pipeline: in recent runs, roughly half
of the questions that passed all five pipeline filters were still cut here for
sounding too synthetic.

---

## Key configuration **[example run config]**

The pipeline is configured through a `PipelineConfig` dataclass. Settings from
the natural-multihop run this document was generated from:

```yaml
targets.total_samples: 15                       # total QA pairs to produce
targets.primary_type_distribution: {lookup: 0.0, multi_hop: 1.0}
targets.hop_distribution: {2: 1.0}              # all 2-hop questions
linker.type: "search_agent"                     # or "metadata", "wiki"
linker.search_agent_pct: 1.0                    # fraction using agent linker
linker.search_agent.max_turns: 4
filtering.filters: ["quality_gate", "retrieval_too_easy_llm",
                    "grounding_llm", "hop_count_validity"]
refinement.enabled: true
refinement.max_rounds: 4                        # max regeneration attempts per batch
```

---

## Data flow summary

Tracing a single QA pair through the pipeline:

1. A seed chunk is selected from the corpus profile sample
2. The linker finds 1–3 secondary chunks related to the seed
3. These chunks form an anchor bundle with structural hints
4. The generator LLM receives the bundle and produces a QA pair
5. Deterministic guards validate format and structure
6. The quality gate checks basic question/answer quality
7. The retrieval-too-easy filter checks whether a simple keyword search would
   find the answer
8. The grounding judge verifies the answer is supported by the chunks
9. The hop count judge confirms multi-hop reasoning is required
10. If the item needs refinement, it loops back to step 4 with feedback
11. Accepted items are deduplicated and type-balanced
12. Final items are split into train and eval sets
13. A naturalness judge (Claude Sonnet) scores each question on four
    dimensions and drops anything that sounds synthetic

Each item carries a journey event log recording every stage it passed through,
every verdict it received, and every regeneration attempt — providing full
traceability from seed chunk to final output.
