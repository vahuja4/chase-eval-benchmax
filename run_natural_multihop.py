"""
Generate 5 natural multi-hop QA pairs with improvements:
1. Max 2 hops (not 3-4)
2. Search-agent linker (LLM-assisted linking)
3. Relaxed obfuscation in generation prompt
4. Naturalness judge — rejects contrived questions

Dumps intermediate outputs at every pipeline step for inspection.
"""

import os
import json
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic
from openai import OpenAI

from benchmax.rag.qa_generation.pipeline_config import (
    PipelineConfig,
    PlatformConfig,
    CorpusConfig,
    CorpusContextConfig,
    TargetsConfig,
    LinkerConfig,
    GenerationConfig,
    LLMDirectGenerationConfig,
    FilteringConfig,
    RetrievalLLMFilterConfig,
    GroundingLLMFilterConfig,
    HopCountValidityCfg,
    RefinementConfig,
    OutputConfig,
    MicroBatchConfig,

    LLMEnvFilterConfig,
    RolloutLimits,
    SearchAgentLinkerCfg,
    EnvBundleConfig,
)
from benchmax.rag.qa_generation.pipeline import Pipeline
from benchmax.platform.client import RolloutClient

PROJECT_DIR = Path(__file__).parent

llm_key = os.environ["LLM_API_KEY"]
llm_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
anthropic_key = os.environ["ANTHROPIC_API_KEY"]
anthropic_url = "https://api.anthropic.com/v1"

# --- Relaxed generation prompt (improvement #3) ---
NATURAL_MULTIHOP_TEMPLATE = (
    "Your task is to generate a multi_hop question that requires "
    "{target_hop_count} search steps to answer by combining information from the provided chunks.\n\n"
    "You must first reason inside <think> and </think>:\n"
    "1. Read the chunks and identify the NATURAL connection between them — what real-world user scenario would genuinely need both pieces of information?\n"
    "2. Draft a question that a real Chase customer would actually ask.\n"
    "3. Verify the question is concise (under 35 words), has a single coherent intent, and sounds like something typed into a search bar or asked to a support agent.\n\n"
    "Corpus summary:\n{corpus_summary}\n\n"
    "Primary chunk:\n{primary_chunk}\n\n"
    "Secondary chunks:\n{secondary_chunks}\n\n"
    "[[if evidence_chain]]How these chunks connect (from linking analysis):\n"
    "{evidence_chain}\n\n[[endif]]"
    "[[if failed_question]]Failed question:\n{failed_question}\n\n[[endif]]"
    "[[if failed_answer]]Failed answer:\n{failed_answer}\n\n[[endif]]"
    "[[if regeneration_prompt]]Feedback:\n{regeneration_prompt}\n\n[[endif]]"
    "Requirements:\n"
    "- NATURALNESS IS THE #1 PRIORITY. The question must sound like something a real person would ask.\n"
    "- Bad: 'If someone used the same account in two different ways during one statement period — first for everyday buying, and second to pull out borrowed cash...' (manufactured scenario, 60+ words)\n"
    "- Good: 'Does a cash advance on my credit card still get a grace period like regular purchases?' (natural, concise, real intent)\n"
    "- Bad: 'I'm advising a first-time borrower who wants to improve their chances before applying...' (role-playing, over-specified)\n"
    "- Good: 'What should I do to build credit before applying for my first Chase card?' (direct, natural)\n"
    "- The question MUST require information from multiple chunks to fully answer — not just one.\n"
    "- If the chunks don't have a natural connection that a real user would care about, return cannot_generate.\n"
    "- Keep the question under 35 words. One sentence. No sub-questions joined by 'and'.\n"
    "- The answer must be grounded in the exact language of the source chunks. Do NOT paraphrase the answer.\n"
    "- Use only chunk evidence; do not use outside knowledge.\n"
    "- Output exactly one question and one answer.\n"
    "- In chunks_used, list the indices of chunks you referenced (0=primary, 1+=secondary).\n"
    "- CRITICAL: If the provided chunks cannot support a natural multi-hop question "
    "(e.g., they are completely unrelated or the connection is forced), "
    'return `{{"status": "cannot_generate", "reason": "<brief explanation>"}}` instead.\n\n'
    "First output your reasoning in <think>...</think>, then provide:\n"
    '```json\n{{"question": "...", "answer": "...", "answering_steps": "...", "chunks_used": [0, 1, ...]}}\n```'
)

# --- Naturalness judge (improvement #4) ---
NATURALNESS_JUDGE_PROMPT = """You are evaluating whether a question sounds natural — like something a real person would type or ask.

Question: {question}

Score this question on a 0.0–1.0 scale across these dimensions, then give an overall score:

1. **Single intent** (0–1): Does this read as ONE coherent thing the person wants to know? Or does it stitch together multiple unrelated sub-questions?
2. **Conciseness** (0–1): Is it reasonably short? Real users don't write 50+ word questions with embedded clauses.
3. **Natural phrasing** (0–1): Does it sound like something you'd type into a search bar or ask a support agent? Red flags: "If someone used X in two different ways...", role-playing scenarios ("I'm advising a first-time borrower who..."), excessive hedging.
4. **Plausible intent** (0–1): Is there a realistic reason a single person would ask exactly this? Or was it manufactured to connect unrelated topics?

Respond in JSON:
```json
{{"single_intent": 0.0, "conciseness": 0.0, "natural_phrasing": 0.0, "plausible_intent": 0.0, "overall": 0.0, "reasoning": "..."}}
```

The overall score should be the minimum of the four dimension scores (one bad dimension fails the whole question)."""


def judge_naturalness(client: Anthropic, question: str, model: str = "claude-sonnet-5") -> dict:
    """Run the naturalness judge on a question. Returns scores dict."""
    import re
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system="You are a question naturalness evaluator. Be strict. Respond with JSON only.",
        messages=[
            {"role": "user", "content": NATURALNESS_JUDGE_PROMPT.format(question=question)},
        ],
    )
    raw = response.content[0].text or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {"overall": 0.0, "reasoning": "Failed to parse judge response"}


# ---------------------------------------------------------------------------
# Helpers: serialize anchor bundles / chunks for the step-by-step dump
# ---------------------------------------------------------------------------

def _serialize_chunk(chunk) -> dict:
    """Extract readable fields from a chunk object."""
    if isinstance(chunk, dict):
        return chunk
    out = {}
    for attr in ("hash", "content", "metadata", "doc_id", "chunk_index"):
        if hasattr(chunk, attr):
            val = getattr(chunk, attr)
            if attr == "content" and len(str(val)) > 500:
                val = str(val)[:500] + "..."
            out[attr] = val
    if hasattr(chunk, "chunk_str"):
        text = chunk.chunk_str()
        out["text_preview"] = text[:500] + ("..." if len(text) > 500 else "")
    return out


def _serialize_anchor(anchor) -> dict:
    """Serialize an AnchorBundle for the step dump."""
    out = {}
    if hasattr(anchor, "primary_chunk"):
        out["primary_chunk"] = _serialize_chunk(anchor.primary_chunk)
    if hasattr(anchor, "secondary_chunks"):
        out["secondary_chunks"] = [_serialize_chunk(c) for c in anchor.secondary_chunks]
    if hasattr(anchor, "structural_hints"):
        hints = dict(anchor.structural_hints) if anchor.structural_hints else {}
        out["structural_hints"] = {
            k: (str(v)[:300] + "..." if len(str(v)) > 300 else str(v))
            for k, v in hints.items()
        }
    return out


def dump_step(out_dir: Path, step_name: str, data, *, indent=2):
    """Write a step's data to a JSON file for inspection."""
    path = out_dir / f"step_{step_name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)
    print(f"  -> Saved {path}")


# --- Pipeline config ---
cfg = PipelineConfig(
    platform=PlatformConfig(
        llm_api_key=llm_key,
        llm_base_url=llm_url,
    ),
    corpus=CorpusConfig(
        corpus_name="chase_help_2026_05_27",
        corpus_id="6558ec44-c948-4ed0-a099-63dd786078ad",
        min_chunk_chars=400,
    ),
    corpus_context=CorpusContextConfig(
        enabled=True,
        description="Chase.com public help and product articles covering credit cards, banking, auto loans, mortgages, and investments.",
    ),
    targets=TargetsConfig(
        total_samples=20,
        primary_type_distribution={"lookup": 0.0, "multi_hop": 1.0},
        hop_distribution={1: 0.0, 2: 1.0},
    ),
    linker=LinkerConfig(
        type="search_agent",
        search_agent_pct=1.0,
        search_agent=SearchAgentLinkerCfg(
            max_turns=4,
            max_tool_calls=4,
            max_completion_tokens=3072,
            fallback_to_metadata=True,
            auto_scale_turns=True,
            env_bundle=EnvBundleConfig(
                env_cls_file=str(PROJECT_DIR / "linker_env_cls.pkl"),
                env_metadata_file=str(PROJECT_DIR / "linker_env_metadata.json"),
            ),
        ),
    ),
    generation=GenerationConfig(
        mode="llm_direct",
        llm_direct=LLMDirectGenerationConfig(
            model="gpt-5.4",
            api_key=llm_key,
            base_url=llm_url,
            prompt_templates_by_qa_type={
                "multi_hop": NATURAL_MULTIHOP_TEMPLATE,
            },
        ),
    ),
    filtering=FilteringConfig(
        filters=[
            "quality_gate",
            "retrieval_too_easy_llm",
            "grounding_llm",
            "hop_count_validity",
        ],
        retrieval_llm=RetrievalLLMFilterConfig(
            judge_model="gpt-5.4",
            judge_base_url=llm_url,
        ),
        grounding_llm=GroundingLLMFilterConfig(
            judge_model="gpt-5.4",
            judge_base_url=llm_url,
        ),
        hop_count_validity=HopCountValidityCfg(
            judge_model="gpt-5.4",
            judge_base_url=llm_url,
        ),
    ),
    refinement=RefinementConfig(
        enabled=True,
        model="gpt-5.4",
        max_refinements_per_item=1,
    ),
    output=OutputConfig(dir="outputs/natural_multihop_batch4"),
    micro_batch=MicroBatchConfig(resume=False),
)

cfg.resolve_api_keys()


def _rollout_factory(cfg):
    return RolloutClient(api_key=cfg.platform.api_key)


out_dir = Path("outputs/natural_multihop_batch4")
out_dir.mkdir(parents=True, exist_ok=True)

print("=" * 60)
print("NATURAL MULTI-HOP EXPERIMENT")
print("=" * 60)
print("Improvements applied:")
print("  1. Max 2 hops (no 3-4 hop contrivance)")
print("  2. Search-agent linker (LLM-assisted linking)")
print("  3. Relaxed obfuscation (naturalness > difficulty)")
print("  4. Naturalness judge (Sonnet, cross-model)")
print(f"  5. Retrieval-too-easy filter (keyword overlap + LLM judge)")
print(f"  Target: 10 candidates")
print("=" * 60)

# ===== Run the pipeline =====
pipeline = Pipeline(cfg, rollout_client_factory=_rollout_factory)
result = pipeline.run()

# ===================================================================
# STEP-BY-STEP OUTPUT DUMPS
# ===================================================================

# --- Step 1: Raw candidates (pre-filter) ---
raw_candidates = result.get("raw_candidates", [])
print(f"\n{'='*60}")
print(f"STEP 1: RAW CANDIDATES — {len(raw_candidates)} generated")
print(f"{'='*60}")
raw_dump = []
for i, rc in enumerate(raw_candidates):
    entry = {
        "index": i,
        "question": rc.get("question", ""),
        "answer": rc.get("answer", ""),
        "qa_type": rc.get("qa_type", ""),
        "min_hop_count": rc.get("min_hop_count"),
        "reference_chunks": [
            {
                "id": ch.get("id", ""),
                "content_preview": str(ch.get("content", ""))[:300],
                "metadata": ch.get("metadata", {}),
            }
            for ch in rc.get("reference_chunks", [])
        ],
    }
    raw_dump.append(entry)
    print(f"\n  [{i+1}] Q: {entry['question'][:100]}")
    print(f"      A: {entry['answer'][:120]}...")
    print(f"      Chunks: {len(rc.get('reference_chunks', []))}")

dump_step(out_dir, "1_raw_candidates", raw_dump)

# --- Step 2: Linking details (from generation_metadata in filtered+rejected) ---
print(f"\n{'='*60}")
print("STEP 2: LINKING DETAILS (anchor bundles)")
print(f"{'='*60}")
all_items = result.get("filtered_dataset", []) + result.get("rejected_dataset", [])
linking_dump = []
for i, item in enumerate(all_items):
    gen_meta = item.get("generation_metadata", {})
    anchor = gen_meta.get("anchor_bundle")
    linking_hints = gen_meta.get("linking_hints", {})
    entry = {
        "index": i,
        "task_id": gen_meta.get("task_id", ""),
        "seed_chunk_id": gen_meta.get("seed_chunk_id", ""),
        "question": item.get("question", "")[:100],
        "linking_hints": linking_hints,
    }
    if anchor is not None:
        entry["anchor_bundle"] = _serialize_anchor(anchor)
    linking_dump.append(entry)
    evidence = ""
    if anchor and hasattr(anchor, "structural_hints"):
        evidence = (anchor.structural_hints or {}).get("evidence_chain", "")
    n_secondary = 0
    if anchor and hasattr(anchor, "secondary_chunks"):
        n_secondary = len(anchor.secondary_chunks)
    print(f"\n  [{i+1}] task={gen_meta.get('task_id', '?')}")
    print(f"      seed={gen_meta.get('seed_chunk_id', '?')[:40]}")
    print(f"      secondary_chunks={n_secondary}")
    if evidence:
        print(f"      evidence_chain: {str(evidence)[:150]}...")
    if linking_hints:
        print(f"      linking_hints: {json.dumps(linking_hints, default=str)[:150]}")

dump_step(out_dir, "2_linking_details", linking_dump)

# --- Step 3: Filter results (which passed, which rejected, why) ---
passed_items = result.get("filtered_dataset", [])
rejected_items = result.get("rejected_dataset", [])
print(f"\n{'='*60}")
print(f"STEP 3: FILTER RESULTS — {len(passed_items)} passed, {len(rejected_items)} rejected")
print(f"{'='*60}")

filter_dump = {"passed": [], "rejected": []}
for i, item in enumerate(passed_items):
    scores = item.get("eval_scores", {})
    entry = {
        "index": i,
        "question": item.get("question", ""),
        "answer": item.get("answer", ""),
        "eval_scores": scores,
        "filter_status": item.get("filter_status"),
        "journey_events": item.get("journey_events", []),
    }
    filter_dump["passed"].append(entry)
    print(f"\n  PASS [{i+1}] Q: {item['question'][:90]}")
    print(f"       grounding={scores.get('grounding', '?')} "
          f"hop_validity={scores.get('hop_validity', '?')} "
          f"composite={scores.get('composite', '?')}")

for i, item in enumerate(rejected_items):
    entry = {
        "index": i,
        "question": item.get("question", ""),
        "filter_status": item.get("filter_status"),
        "filter_reason": item.get("filter_reason"),
        "filter_reasoning": item.get("filter_reasoning", "")[:300],
        "journey_events": item.get("journey_events", []),
    }
    filter_dump["rejected"].append(entry)
    print(f"\n  REJECT [{i+1}] Q: {item.get('question', '?')[:80]}")
    print(f"       reason: {item.get('filter_reason', '?')}")
    print(f"       detail: {str(item.get('filter_reasoning', ''))[:120]}")

dump_step(out_dir, "3_filter_results", filter_dump)

# --- Step 4: Pipeline stats ---
stats = result.get("stats", {})
print(f"\n{'='*60}")
print("STEP 4: PIPELINE STATS")
print(f"{'='*60}")
for k, v in stats.items():
    if isinstance(v, dict):
        print(f"  {k}:")
        for kk, vv in v.items():
            print(f"    {kk}: {vv}")
    else:
        print(f"  {k}: {v}")

dump_step(out_dir, "4_pipeline_stats", stats)

# ===== Post-pipeline naturalness filter (improvement #4) =====
print(f"\n{'='*60}")
print(f"STEP 5: NATURALNESS JUDGE (Sonnet) — {len(passed_items)} items")
print(f"{'='*60}")

judge_client = Anthropic(api_key=anthropic_key)

scored_items = []
for i, item in enumerate(passed_items):
    question = item.get("question", "")
    scores = judge_naturalness(judge_client, question)
    overall = float(scores.get("overall", 0.0))
    print(f"\n  [{i+1}] overall={overall:.2f} | {question[:80]}")
    print(f"       single_intent={scores.get('single_intent', '?')}"
          f"  conciseness={scores.get('conciseness', '?')}"
          f"  phrasing={scores.get('natural_phrasing', '?')}"
          f"  plausible={scores.get('plausible_intent', '?')}")
    print(f"       reasoning: {scores.get('reasoning', '')[:150]}")
    scored_items.append({
        **item,
        "naturalness_scores": scores,
        "naturalness_overall": overall,
    })

dump_step(out_dir, "5_naturalness_scores", [
    {
        "question": s["question"],
        "naturalness_overall": s["naturalness_overall"],
        "naturalness_scores": s["naturalness_scores"],
    }
    for s in scored_items
])

# Filter and sort by naturalness
NATURALNESS_THRESHOLD = 0.6
natural_items = [
    item for item in scored_items
    if item["naturalness_overall"] >= NATURALNESS_THRESHOLD
]
natural_items.sort(key=lambda x: x["naturalness_overall"], reverse=True)

# Take top 5
final_items = natural_items[:5]

# --- Step 6: Final output ---
print(f"\n{'='*60}")
print(f"STEP 6: FINAL OUTPUT — {len(final_items)} natural multi-hop questions")
print(f"  (from {len(passed_items)} pipeline-passed, "
      f"{len(natural_items)} passed naturalness >= {NATURALNESS_THRESHOLD})")
print(f"{'='*60}")

for i, item in enumerate(final_items):
    print(f"\n--- Question {i+1} (naturalness={item['naturalness_overall']:.2f}) ---")
    print(f"Q: {item['question']}")
    print(f"A: {item['answer'][:200]}...")
    print(f"Chunks: {len(item.get('reference_chunks', []))}")
    for j, ch in enumerate(item.get("reference_chunks", [])):
        print(f"  chunk[{j}]: {str(ch.get('content', ''))[:120]}...")
    print(f"Scores: grounding={item.get('eval_scores', {}).get('grounding', '?')}, "
          f"hop_validity={item.get('eval_scores', {}).get('hop_validity', '?')}, "
          f"naturalness={item['naturalness_overall']:.2f}")

# Save results
with open(out_dir / "natural_multihop.jsonl", "w") as f:
    for item in final_items:
        f.write(json.dumps(item, default=str) + "\n")

with open(out_dir / "all_scored.jsonl", "w") as f:
    for item in scored_items:
        f.write(json.dumps(item, default=str) + "\n")

# Save full rejected set for debugging
with open(out_dir / "rejected.jsonl", "w") as f:
    for item in rejected_items:
        f.write(json.dumps(item, default=str) + "\n")

print(f"\nSaved {len(final_items)} final items to {out_dir / 'natural_multihop.jsonl'}")
print(f"Saved {len(scored_items)} scored items to {out_dir / 'all_scored.jsonl'}")
print(f"Saved {len(rejected_items)} rejected items to {out_dir / 'rejected.jsonl'}")
print(f"\nStep-by-step dumps in {out_dir}/step_*.json")
