"""
Step 5 runner — configures the pipeline in Python (no YAML) and runs
the 30-item calibration batch.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from benchmax.rag.qa_generation.pipeline_config import (
    PipelineConfig,
    PlatformConfig,
    CorpusConfig,
    CorpusContextConfig,
    TargetsConfig,
    LinkerConfig,
    GenerationConfig,
    FilteringConfig,
    RetrievalLLMFilterConfig,
    GroundingLLMFilterConfig,
    HopCountValidityCfg,
    RefinementConfig,
    OutputConfig,
    MicroBatchConfig,
    EnvBundleConfig,
    LLMEnvFilterConfig,
    RolloutLimits,
)
from benchmax.rag.qa_generation.pipeline import Pipeline
from benchmax.platform.client import RolloutClient

PROJECT_DIR = Path(__file__).parent

from src.bundles import require_bundle
ENV_PKL, ENV_META = require_bundle("env")

llm_key = os.environ["LLM_API_KEY"]
llm_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
anthropic_key = os.environ["ANTHROPIC_API_KEY"]
anthropic_url = "https://api.anthropic.com/v1"

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
        total_samples=30,
        primary_type_distribution={"lookup": 0.34, "multi_hop": 0.66},
        hop_distribution={1: 0.34, 2: 0.33, 3: 0.33},
    ),
    linker=LinkerConfig(
        type="metadata",
        search_agent_pct=1.0,
    ),
    generation=GenerationConfig(mode="llm_direct"),
    filtering=FilteringConfig(
        filters=[
            "quality_gate",
            "retrieval_too_easy_llm",
            "grounding_llm",
            "hop_count_validity",
            "env_rollout",
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
        env_rollout=LLMEnvFilterConfig(
            enabled=True,
            model="claude-sonnet-4-6",
            api_key=anthropic_key,
            base_url=anthropic_url,
            judge_model="gpt-5.4",
            judge_api_key=llm_key,
            judge_base_url=llm_url,
            env_bundle=EnvBundleConfig(
                env_cls_file=str(ENV_PKL),
                env_metadata_file=str(ENV_META),
            ),
            rollout_limits=RolloutLimits(
                max_turns=6,
                max_tool_calls=8,
                max_completion_tokens=2048,
                timeout=120.0,
            ),
        ),
    ),
    refinement=RefinementConfig(
        enabled=True,
        model="gpt-5.4",
        max_refinements_per_item=1,
    ),
    output=OutputConfig(dir="outputs/calibration_30"),
    micro_batch=MicroBatchConfig(resume=True),
)

cfg.resolve_api_keys()


def _rollout_factory(cfg):
    return RolloutClient(api_key=cfg.platform.api_key)


pipeline = Pipeline(cfg, rollout_client_factory=_rollout_factory)

# --- Dump corpus profile before running generation/filtering ---
import json as _json
import time as _time

context = pipeline.prepare_context()

profile = context.profile
census = context.get("census")
corpus_profile_data = context.get("corpus_profile", {})

dump = {
    "dumped_at": _time.strftime("%Y-%m-%dT%H:%M:%S"),
    "corpus_summary": profile.corpus_summary if profile else "",
    "corpus_description": profile.corpus_description if profile else "",
    "corpus_queries": profile.corpus_queries if profile else [],
    "search_modes": sorted(profile.search_modes) if profile else [],
    "best_search_mode": profile.best_search_mode if profile else "",
    "capabilities": {
        "has_document_ids": profile.capabilities.has_document_ids,
        "has_section_headers": profile.capabilities.has_section_headers,
        "has_sequential_links": profile.capabilities.has_sequential_links,
        "has_dates": profile.capabilities.has_dates,
    } if profile else {},
    "entity_count": len(profile.entity_patterns) if profile else 0,
    "entities": [
        {
            "name": e.name,
            "document_frequency": round(e.document_frequency, 4),
            "quality_score": round(e.quality_score, 4),
            "chunk_count": len(profile.entity_chunk_index.get(e.name.lower(), set())),
        }
        for e in (profile.entity_patterns if profile else [])
    ],
    "entity_cooccurrence_count": len(profile.entity_cooccurrence) if profile else 0,
    "top_cooccurrences": sorted(
        [
            {"pair": list(k), "count": v}
            for k, v in (profile.entity_cooccurrence or {}).items()
        ],
        key=lambda x: x["count"],
        reverse=True,
    )[:50],
    "corpus_pool_size": len(context.get("corpus_pool", [])),
    "seed_chunk_count": len(context.get("seed_chunk_lookup", {})),
    "census": {
        "chunk_count": getattr(census, "chunk_count", None),
        "strata": getattr(census, "strata", None),
        "linkability_p50": getattr(census, "linkability_p50", None),
        "linkability_p75": getattr(census, "linkability_p75", None),
        "header_prevalence": getattr(census, "header_prevalence", None),
    } if census else None,
    "corpus_profile_raw": corpus_profile_data,
}

out_dir = Path(cfg.output.dir)
out_dir.mkdir(parents=True, exist_ok=True)
dump_path = out_dir / "corpus_profile_dump.json"
with open(dump_path, "w") as f:
    _json.dump(dump, f, indent=2, default=str)
print(f"Corpus profile dumped to {dump_path}")

result = pipeline.run_from_context(context)

# --- Print calibration report ---
stats = result.get("stats", {})
env_stats = stats.get("env_filter_stats") or result.get("env_filter_stats", {})

print("\n" + "=" * 60)
print("CALIBRATION REPORT (30 items)")
print("=" * 60)
print(f"Total passed:   {result.get('passed_count', '?')}")
print(f"Total rejected: {result.get('rejected_count', '?')}")
print(f"Total regen'd:  {result.get('regenerated_count', '?')}")

if env_stats:
    print(f"\nEnv rollout stats:")
    for k, v in env_stats.items():
        print(f"  {k}: {v}")

print(f"\nOutput dir: {cfg.output.dir}")
print("=" * 60)
