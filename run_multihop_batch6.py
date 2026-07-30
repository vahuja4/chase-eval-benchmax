"""
Batch 6: natural multi-hop QA pairs on the Castform (postgres) path.

Default 50 items -> outputs/natural_multihop_batch6/. A non-default
--total N writes to outputs/natural_multihop_batch6_pilotN/ so pilots
never clobber the full run (10-item pilot: _pilot10, 2026-07-30).

NEW length regime vs batches 1-5 (results NOT comparable to prior batches):
- generation prompt targets one sentence, <=20 words (template v2)
- deterministic query_length_cap filter: >25 words -> needs_refinement
- naturalness judge conciseness scored by word bands (rubric v2),
  enforced in code; overall = min(dimensions)

Dedup: pre-seeds against the pipeline-passed superset of ALL prior
batches; every collision is logged with its originating seed file to
the run dir dedup_collisions.jsonl.

Configure-and-verify (no Castform credits, no generation spend):
    python run_multihop_batch6.py --dry-run
Launch (per notes/castform_runbook.md; ~1 rollout credit + OpenAI calls
per item; stop after the first batch to review cost, resume=True):
    python run_multihop_batch6.py
"""

import argparse
import dataclasses
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from anthropic import Anthropic

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
    SearchAgentLinkerCfg,
    EnvBundleConfig,
)
from benchmax.rag.qa_generation.pipeline import Pipeline
from benchmax.platform.client import RolloutClient

from src.bundles import require_bundle
from src.dedup_attribution import seed_and_instrument
from src.query_length import (
    HARD_CAP,
    JUDGE_RUBRIC_VERSION,
    PROMPT_TARGET,
    REFINEMENT_FEEDBACK,
    STAGE_NAME,
    CONCISENESS_BANDS,
    CONCISENESS_FLOOR,
    apply_banded_scores,
    count_words,
    install_query_length_filter,
)

PROJECT_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Backend: this run is defined as the Castform path. Explicit, not ambient.
# ---------------------------------------------------------------------------

SEARCH_BACKEND = "postgres"
_ambient = os.environ.get("SEARCH_BACKEND")
if _ambient and _ambient != SEARCH_BACKEND:
    raise SystemExit(
        f"run_multihop_batch6.py is a Castform-path run (backend={SEARCH_BACKEND!r}) "
        f"but SEARCH_BACKEND={_ambient!r} is set. Unset it or set it to "
        f"{SEARCH_BACKEND!r}."
    )
LINKER_PKL, LINKER_META = require_bundle("linker_env", backend=SEARCH_BACKEND)

llm_key = os.environ["LLM_API_KEY"]
llm_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
anthropic_key = os.environ["ANTHROPIC_API_KEY"]
if not os.environ.get("PLATFORM_API_KEY"):
    raise SystemExit(
        "PLATFORM_API_KEY is not set — required on the Castform path "
        "(chunk source, retrieval filter, and linker rollouts). See "
        "notes/castform_runbook.md."
    )

# ---------------------------------------------------------------------------
# Load prior questions for dedup (pipeline-passed superset of ALL batches)
# ---------------------------------------------------------------------------

PRIOR_FILES = [
    "outputs/natural_multihop/all_scored.jsonl",
    "outputs/natural_multihop_batch4/all_scored.jsonl",
    "outputs/retrieval_filtered_batch3/all_scored.jsonl",
    # batch5 never wrote all_scored.jsonl; its pipeline-passed superset is
    # the checkpoint plus the post-judge split (seed overlap is harmless).
    "outputs/natural_multihop_batch5/.checkpoints/checkpoint_passed.jsonl",
    "outputs/natural_multihop_batch5/train.jsonl",
    "outputs/natural_multihop_batch5/eval.jsonl",
    # batch-6 increments: each completed run's pipeline-passed superset
    # seeds the next, so successive runs never repeat questions.
    "outputs/natural_multihop_batch6_pilot10/all_scored.jsonl",
    "outputs/natural_multihop_batch6_run2/all_scored.jsonl",
]

prior_entries: list[tuple[str, str]] = []  # (source_file, question)
prior_counts: dict[str, int] = {}
for fpath in PRIOR_FILES:
    p = PROJECT_DIR / fpath
    if not p.exists():
        raise SystemExit(
            f"Dedup seed file missing: {p} — refusing to run with a "
            f"partial dedup seed. Fix PRIOR_FILES or restore the file."
        )
    n = 0
    with open(p) as f:
        for line in f:
            line = line.strip()
            if line:
                q = json.loads(line).get("question", "")
                if q:
                    prior_entries.append((fpath, q))
                    n += 1
    prior_counts[fpath] = n

print(f"Loaded {len(prior_entries)} prior questions for dedup "
      f"({len(PRIOR_FILES)} files)")


# --- Generation prompt, template v2 (length-constrained) ---
NATURAL_MULTIHOP_TEMPLATE = (
    "Your task is to generate a multi_hop question that requires "
    "{target_hop_count} search steps to answer by combining information from the provided chunks.\n\n"
    "You must first reason inside <think> and </think>:\n"
    "1. Read the chunks and identify the NATURAL connection between them — what real-world user scenario would genuinely need both pieces of information?\n"
    "2. Draft a question that a real Chase customer would actually ask.\n"
    "3. Verify the question is one sentence of 20 words or fewer, has a single coherent intent, and sounds like something typed into a search bar or asked of a support agent.\n\n"
    "Corpus summary:\n{corpus_summary}\n\n"
    "Primary chunk:\n{primary_chunk}\n\n"
    "Secondary chunks:\n{secondary_chunks}\n\n"
    "[[if evidence_chain]]How these chunks connect (from linking analysis):\n"
    "{evidence_chain}\n\n[[endif]]"
    "[[if failed_question]]Failed question:\n{failed_question}\n\n[[endif]]"
    "[[if failed_answer]]Failed answer:\n{failed_answer}\n\n[[endif]]"
    "[[if regeneration_prompt]]Feedback:\n{regeneration_prompt}\n\n"
    "When rewriting to address this feedback, keep the question to one sentence "
    "of 20 words or fewer — do not add qualifiers or scenario setup to satisfy "
    "the feedback.\n\n[[endif]]"
    "Requirements:\n"
    "- NATURALNESS IS THE #1 PRIORITY. The question must sound like something a real person would ask.\n"
    "- Bad: 'If someone used the same account in two different ways during one statement period — first for everyday buying, and second to pull out borrowed cash...' (manufactured scenario, 60+ words)\n"
    "- Good: 'Does a cash advance on my credit card still get a grace period like regular purchases?' (natural, concise, real intent)\n"
    "- Bad: 'I'm advising a first-time borrower who wants to improve their chances before applying...' (role-playing, over-specified)\n"
    "- Good: 'What should I do to build credit before applying for my first Chase card?' (direct, natural)\n"
    "- The question MUST require information from multiple chunks to fully answer — not just one.\n"
    "- If the chunks don't have a natural connection that a real user would care about, return cannot_generate.\n"
    "- STYLE CONSTRAINT: one sentence, 20 words or fewer, phrased like a real customer's search query or support question. No sub-questions joined by 'and', no stacked qualifiers, no role-play setups (\"I'm advising...\", \"Suppose someone...\").\n"
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

# --- Naturalness judge, rubric v2 — shared module (see known_issues #7) ---
from src.naturalness import (
    JUDGE_MODEL,
    NATURALNESS_JUDGE_PROMPT,
    NATURALNESS_THRESHOLD,
    judge_naturalness,
)


def verify_judge_model(client: Anthropic, model_id: str) -> None:
    """Fail fast (free metadata call) if the judge model id is invalid."""
    ids = [m.id for m in client.models.list(limit=100)]
    if model_id not in ids:
        raise SystemExit(
            f"Judge model {model_id!r} not found in the live Anthropic model "
            f"list ({len(ids)} models). Aborting before any generation spend."
        )
    print(f"  Judge model verified against live API: {model_id}")


# ---------------------------------------------------------------------------
# Helpers (unchanged from batch5)
# ---------------------------------------------------------------------------

def _serialize_chunk(chunk) -> dict:
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
    path = out_dir / f"step_{step_name}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=indent, default=str)
    print(f"  -> Saved {path}")


# ---------------------------------------------------------------------------
# Monkey-patches: custom filter registration + dedup pre-seed w/ attribution
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--dry-run", action="store_true",
                    help="Verify config, bundles, judge model, and dedup seed; "
                         "write run_config.json; exit before the pipeline.")
parser.add_argument("--total", type=int, default=50,
                    help="Number of accepted items to target (default 50). "
                         "Non-default totals get their own suffixed output dir. "
                         "NOTE: benchmax keys checkpoint-resume on a config hash "
                         "that includes total_samples — a later run with a "
                         "different --total starts fresh, it does not resume.")
parser.add_argument("--name", default="",
                    help="Output-dir suffix override: outputs/natural_multihop_"
                         "batch6_<name>. Default: none for --total 50, "
                         "pilot<N> otherwise. Use e.g. --name run2 for "
                         "incremental production runs.")
args = parser.parse_args()

_suffix = args.name or ("" if args.total == 50 else f"pilot{args.total}")
RUN_NAME = "natural_multihop_batch6" + (f"_{_suffix}" if _suffix else "")

install_query_length_filter()

# Castform workers return OpenAI-format tool calls, which the installed
# benchmax linker cannot parse — without this, every anchor bundle comes
# back empty ("no_queries") and no multi-hop item can pass. See
# notes/known_issues.md #6.
from src.rollout_compat import install_openai_toolcall_extraction
install_openai_toolcall_extraction()

out_dir = Path("outputs") / RUN_NAME
out_dir.mkdir(parents=True, exist_ok=True)
COLLISION_LOG = out_dir / "dedup_collisions.jsonl"

_original_run = Pipeline.run

def _patched_run(self):
    from benchmax.rag.qa_generation.transformers.dedup import IncrementalDeduplicator

    _original_init = IncrementalDeduplicator.__init__

    def _seeded_init(dedup_self, *args, **kwargs):
        _original_init(dedup_self, *args, **kwargs)
        seed_and_instrument(dedup_self, prior_entries, COLLISION_LOG)
        print(f"  [dedup] Pre-seeded with {len(prior_entries)} prior questions "
              f"(collision log: {COLLISION_LOG})")

    IncrementalDeduplicator.__init__ = _seeded_init
    try:
        return _original_run(self)
    finally:
        IncrementalDeduplicator.__init__ = _original_init

Pipeline.run = _patched_run

# Disable auto_tune — it reduces multi_hop ratio based on corpus linkability,
# but we want 100% multi_hop regardless.
import benchmax.rag.qa_generation.pipeline as _pipeline_mod
_pipeline_mod.auto_tune = lambda census, profile, cfg: {}


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
        total_samples=args.total,
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
                env_cls_file=str(LINKER_PKL),
                env_metadata_file=str(LINKER_META),
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
            STAGE_NAME,  # deterministic length cap, before all LLM filters
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
        # 2 (batch5 used 1): the length cap adds refinement pressure; a
        # shared budget of 1 would starve the LLM filters.
        max_refinements_per_item=2,
    ),
    output=OutputConfig(dir=str(out_dir)),
    micro_batch=MicroBatchConfig(
        # Checkpointing ON: serial batches, resumable, checkpoints kept in
        # {out_dir}/.checkpoints/ — stop after the first batch to
        # review cost, then re-run to resume.
        resume=True,
        keep_checkpoints=True,
        max_parallel_batches=1,
    ),
)

cfg.resolve_api_keys()



def _rollout_factory(cfg):
    return RolloutClient(api_key=cfg.platform.api_key)


# ---------------------------------------------------------------------------
# Provenance: run_config.json (written at config time, secrets redacted)
# ---------------------------------------------------------------------------

_SECRET_KEY_RE = re.compile(r"api_key|token|secret|password", re.IGNORECASE)


def _redact(obj):
    if isinstance(obj, dict):
        return {
            k: ("<redacted>" if _SECRET_KEY_RE.search(str(k)) and v else _redact(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT_DIR,
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def write_run_config() -> Path:
    run_config = {
        "run_name": RUN_NAME,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "search_backend": SEARCH_BACKEND,
        "bundle_files": {
            "linker_env_cls": str(LINKER_PKL),
            "linker_env_metadata": str(LINKER_META),
            "metadata_stamp": json.loads(Path(LINKER_META).read_text()),
        },
        "pipeline_config": _redact(dataclasses.asdict(cfg)),
        "length_constraint": {
            "prompt_target_words": PROMPT_TARGET,
            "hard_cap_words": HARD_CAP,
            "filter_stage": STAGE_NAME,
            "refinement_feedback": REFINEMENT_FEEDBACK,
        },
        "judge": {
            "model": JUDGE_MODEL,
            "rubric_version": JUDGE_RUBRIC_VERSION,
            "threshold": NATURALNESS_THRESHOLD,
            "conciseness_bands": {
                "bands_upper_bound_to_score": dict(CONCISENESS_BANDS),
                "floor_above_35_words": CONCISENESS_FLOOR,
            },
            "conciseness_and_overall_enforced_in_code": True,
            "prompt": NATURALNESS_JUDGE_PROMPT,
        },
        "generation_prompt_template": NATURAL_MULTIHOP_TEMPLATE,
        "dedup": {
            "prior_files": prior_counts,
            "total_prior_questions": len(prior_entries),
            "similarity_threshold": 0.70,
            "collision_log": str(COLLISION_LOG),
        },
    }
    path = out_dir / "run_config.json"
    with open(path, "w") as f:
        json.dump(run_config, f, indent=2, default=str)
    print(f"  -> Saved {path}")
    return path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


print("=" * 60)
print("NATURAL MULTI-HOP BATCH 6 — 50 items, Castform path")
print("=" * 60)
print(f"  Backend: {SEARCH_BACKEND} (bundles: {LINKER_PKL.parent})")
print(f"  Target: {cfg.targets.total_samples} samples, 100% multi_hop, 2-hop")
print(f"  Filters: {' → '.join(cfg.filtering.filters)}")
print(f"  Length regime: prompt <= {PROMPT_TARGET} words, hard cap {HARD_CAP}")
print(f"  Judge: {JUDGE_MODEL}, rubric {JUDGE_RUBRIC_VERSION}, "
      f"threshold {NATURALNESS_THRESHOLD}")
print(f"  Prior questions for dedup: {len(prior_entries)}")
print(f"  Checkpoints: {out_dir}/.checkpoints/ (resume=True)")
print(f"  Cost note: ~1 Castform rollout credit + OpenAI calls per item")
print("=" * 60)

write_run_config()

judge_client = Anthropic(api_key=anthropic_key)

if args.dry_run:
    print("\nDRY RUN — verifying, not launching")
    verify_judge_model(judge_client, JUDGE_MODEL)
    # Prove the full filter chain (incl. the custom stage) resolves.
    names, chain = _pipeline_mod._build_filter_chain(cfg, source=None)
    print(f"  Filter chain resolves: {names}")
    assert names[0] == STAGE_NAME, "length cap must be the first filter stage"
    print("  Dry run OK. Launch with: python run_multihop_batch6.py")
    sys.exit(0)

# ===== Run the pipeline =====
pipeline = Pipeline(cfg, rollout_client_factory=_rollout_factory)
result = pipeline.run()

# ===================================================================
# STEP-BY-STEP OUTPUT DUMPS (batch5 format)
# ===================================================================

# --- Step 1: Raw candidates ---
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

# --- Step 2: Linking details ---
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

# --- Step 3: Filter results ---
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

# ===== Post-pipeline naturalness filter (rubric v2) =====
print(f"\n{'='*60}")
print(f"STEP 5: NATURALNESS JUDGE ({JUDGE_MODEL}, rubric v2) — {len(passed_items)} items")
print(f"{'='*60}")

scored_items = []
for i, item in enumerate(passed_items):
    question = item.get("question", "")
    scores = judge_naturalness(judge_client, question)
    overall = float(scores.get("overall", 0.0))
    print(f"\n  [{i+1}] overall={overall:.2f} ({count_words(question)} words) | {question[:80]}")
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
natural_items = [
    item for item in scored_items
    if item["naturalness_overall"] >= NATURALNESS_THRESHOLD
]
natural_items.sort(key=lambda x: x["naturalness_overall"], reverse=True)

final_items = natural_items

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

with open(out_dir / "rejected.jsonl", "w") as f:
    for item in rejected_items:
        f.write(json.dumps(item, default=str) + "\n")

# Train/eval split (80/20, deterministic)
import random as _rng
_rng.seed(42)
_shuffled = list(final_items)
_rng.shuffle(_shuffled)
_split_idx = max(1, int(len(_shuffled) * 0.8))
train_items = _shuffled[:_split_idx]
eval_items = _shuffled[_split_idx:]

with open(out_dir / "train.jsonl", "w") as f:
    for item in train_items:
        f.write(json.dumps(item, default=str) + "\n")

with open(out_dir / "eval.jsonl", "w") as f:
    for item in eval_items:
        f.write(json.dumps(item, default=str) + "\n")

print(f"\nSaved {len(final_items)} final items to {out_dir / 'natural_multihop.jsonl'}")
print(f"  Train: {len(train_items)} | Eval: {len(eval_items)}")
print(f"Saved {len(scored_items)} scored items to {out_dir / 'all_scored.jsonl'}")
print(f"Saved {len(rejected_items)} rejected items to {out_dir / 'rejected.jsonl'}")
print(f"Dedup collisions (if any) logged to {COLLISION_LOG}")
print(f"\nStep-by-step dumps in {out_dir}/step_*.json")
