"""Debug: run pipeline with 3 items and intercept linking to dump message format."""

import os
import json
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from benchmax.rag.qa_generation.pipeline_config import (
    PipelineConfig, PlatformConfig, CorpusConfig, CorpusContextConfig,
    TargetsConfig, LinkerConfig, GenerationConfig, LLMDirectGenerationConfig,
    FilteringConfig, RetrievalLLMFilterConfig, GroundingLLMFilterConfig,
    HopCountValidityCfg, RefinementConfig, OutputConfig, MicroBatchConfig,
    SearchAgentLinkerCfg, EnvBundleConfig,
)
from benchmax.rag.qa_generation.pipeline import Pipeline
from benchmax.platform.client import RolloutClient
from benchmax.rag.qa_generation import search_agent_linker as _linker_mod

PROJECT_DIR = Path(__file__).parent

from src.bundles import require_bundle
LINKER_PKL, LINKER_META = require_bundle("linker_env")

llm_key = os.environ["LLM_API_KEY"]
llm_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")

# Monkey-patch _link_with_llm to add debug logging
_original_link_with_llm = _linker_mod.SearchAgentLinker._link_with_llm
_debug_count = 0

def _debug_link_with_llm(self, primary_chunk, hop_count, n_secondaries, reasoning_mode):
    global _debug_count
    _debug_count += 1

    if _debug_count <= 3:
        print(f"\n{'='*60}")
        print(f"DEBUG _link_with_llm call #{_debug_count}")
        print(f"  hop_count={hop_count}, n_secondaries={n_secondaries}")
        print(f"  reasoning_mode={reasoning_mode}")
        print(f"  primary_chunk hash={getattr(primary_chunk, 'hash', '?')[:20]}")

    result = _original_link_with_llm(self, primary_chunk, hop_count, n_secondaries, reasoning_mode)

    if _debug_count <= 3:
        hints = result.structural_hints if hasattr(result, 'structural_hints') else {}
        print(f"  RESULT: secondary_chunks={len(result.secondary_chunks) if hasattr(result, 'secondary_chunks') else '?'}")
        print(f"  RESULT: hints={json.dumps(dict(hints), default=str)[:200]}")
        print(f"{'='*60}\n")

    return result

_linker_mod.SearchAgentLinker._link_with_llm = _debug_link_with_llm

# Also patch _run_rollout to dump messages
_original_run_rollout = _linker_mod.SearchAgentLinker._run_rollout
_rollout_debug_count = 0

def _debug_run_rollout(self, raw_example, *, hop_count=2):
    global _rollout_debug_count
    _rollout_debug_count += 1

    result = _original_run_rollout(self, raw_example, hop_count=hop_count)

    if _rollout_debug_count <= 3:
        print(f"\n  [ROLLOUT DEBUG #{_rollout_debug_count}]")
        print(f"    result keys: {list(result.keys())}")
        messages = result.get("messages", [])
        print(f"    messages count: {len(messages)}")
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")
            content_type = type(content).__name__
            has_tool_calls = "tool_calls" in msg
            print(f"    msg[{i}] role={role} content_type={content_type} len={len(str(content))} has_tool_calls={has_tool_calls}")
            if has_tool_calls:
                tool_calls = msg["tool_calls"]
                print(f"      tool_calls type={type(tool_calls).__name__} len={len(tool_calls) if isinstance(tool_calls, list) else '?'}")
                for j, tc in enumerate(tool_calls[:2]):
                    if isinstance(tc, dict):
                        print(f"      tc[{j}] keys={list(tc.keys())}")
                        func = tc.get("function", {})
                        if isinstance(func, dict):
                            print(f"      tc[{j}] function.name={func.get('name')}")
                            args = func.get("arguments")
                            print(f"      tc[{j}] function.arguments type={type(args).__name__}: {str(args)[:150]}")

        # Test extraction
        queries = _linker_mod._extract_queries(messages)
        print(f"    extracted queries: {queries}")
        assistant_messages = result.get("assistant_messages", [])
        queries2 = _linker_mod._extract_queries(assistant_messages)
        print(f"    extracted from assistant_messages: {queries2}")

    return result

_linker_mod.SearchAgentLinker._run_rollout = _debug_run_rollout

# Disable auto_tune
import benchmax.rag.qa_generation.auto_tune as _auto_tune_mod
_auto_tune_mod.auto_tune = lambda census, profile, cfg: {}
import benchmax.rag.qa_generation.pipeline as _pipeline_mod
_pipeline_mod.auto_tune = lambda census, profile, cfg: {}

NATURAL_MULTIHOP_TEMPLATE = (
    "Your task is to generate a multi_hop question that requires "
    "{target_hop_count} search steps to answer by combining information from the provided chunks.\n\n"
    "Corpus summary:\n{corpus_summary}\n\n"
    "Primary chunk:\n{primary_chunk}\n\n"
    "Secondary chunks:\n{secondary_chunks}\n\n"
    "[[if evidence_chain]]Evidence chain:\n{evidence_chain}\n\n[[endif]]"
    "Requirements:\n"
    "- The question MUST require information from multiple chunks.\n"
    "- Keep the question under 35 words.\n"
    "- The answer must be grounded in the source chunks.\n"
    '```json\n{{"question": "...", "answer": "...", "answering_steps": "...", "chunks_used": [0, 1, ...]}}\n```'
)

cfg = PipelineConfig(
    platform=PlatformConfig(llm_api_key=llm_key, llm_base_url=llm_url),
    corpus=CorpusConfig(
        corpus_name="chase_help_2026_05_27",
        corpus_id="6558ec44-c948-4ed0-a099-63dd786078ad",
        min_chunk_chars=400,
    ),
    corpus_context=CorpusContextConfig(enabled=True),
    targets=TargetsConfig(
        total_samples=3,
        primary_type_distribution={"lookup": 0.0, "multi_hop": 1.0},
        hop_distribution={1: 0.0, 2: 1.0},
    ),
    linker=LinkerConfig(
        type="search_agent",
        search_agent_pct=1.0,
        search_agent=SearchAgentLinkerCfg(
            max_turns=4, max_tool_calls=4, max_completion_tokens=3072,
            fallback_to_metadata=True, auto_scale_turns=True,
            env_bundle=EnvBundleConfig(
                env_cls_file=str(LINKER_PKL),
                env_metadata_file=str(LINKER_META),
            ),
        ),
    ),
    generation=GenerationConfig(
        mode="llm_direct",
        llm_direct=LLMDirectGenerationConfig(
            model="gpt-5.4", api_key=llm_key, base_url=llm_url,
            prompt_templates_by_qa_type={"multi_hop": NATURAL_MULTIHOP_TEMPLATE},
        ),
    ),
    filtering=FilteringConfig(
        filters=["quality_gate", "retrieval_too_easy_llm", "grounding_llm", "hop_count_validity"],
        retrieval_llm=RetrievalLLMFilterConfig(judge_model="gpt-5.4", judge_base_url=llm_url),
        grounding_llm=GroundingLLMFilterConfig(judge_model="gpt-5.4", judge_base_url=llm_url),
        hop_count_validity=HopCountValidityCfg(judge_model="gpt-5.4", judge_base_url=llm_url),
    ),
    refinement=RefinementConfig(enabled=False),
    output=OutputConfig(dir="outputs/debug_linking"),
    micro_batch=MicroBatchConfig(resume=False),
)

cfg.resolve_api_keys()

pipeline = Pipeline(cfg, rollout_client_factory=lambda c: RolloutClient(api_key=c.platform.api_key))
result = pipeline.run()

passed = result.get("filtered_dataset", [])
rejected = result.get("rejected_dataset", [])
print(f"\nFINAL: {len(passed)} passed, {len(rejected)} rejected")
for item in passed + rejected:
    gm = item.get("generation_metadata", {})
    hints = gm.get("linking_hints", {})
    print(f"  Q: {item.get('question', '?')[:80]}")
    print(f"    reason={hints.get('reason', '?')} hop={hints.get('requested_hop_count', '?')}")
