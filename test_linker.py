"""Standalone test of the search-agent linker (without the full pipeline)."""

import os
import json
import time
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from benchmax.rag.corpus.postgres.source import PostgresChunkSource
from benchmax.rag.qa_generation.search_agent_linker import SearchAgentLinker
from benchmax.rag.qa_generation.metadata_linker import MetadataChunkLinker, MetadataLinkerConfig
from benchmax.rag.qa_generation.corpus_profile import CorpusProfile
from benchmax.rag.qa_generation.pipeline_config import SearchAgentLinkerCfg, EnvBundleConfig
from benchmax.platform.client import RolloutClient
from benchmax.platform.credentials import resolve_token_provider

CORPUS_NAME = "chase_help_2026_05_27"
CORPUS_ID = "6558ec44-c948-4ed0-a099-63dd786078ad"

llm_key = os.environ["LLM_API_KEY"]
llm_url = os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1")
platform_key = os.environ.get("PLATFORM_API_KEY", "")

print("Loading corpus source...")
source = PostgresChunkSource(api_key=platform_key, corpus_name=CORPUS_NAME)
source.populate_from_existing_corpus(CORPUS_ID, show_summary=False)
chunks = source.sample_chunks(20, min_chars=400)
print(f"  Sampled {len(chunks)} chunks (min 400 chars)")

print("Building minimal corpus profile...")
profile = CorpusProfile(
    corpus_summary="Chase.com help articles covering credit cards, banking, loans, and investments.",
    corpus_description="Chase.com public help and product articles.",
)

print("Building search client...")
from src.bundles import require_bundle, search_backend
SEARCH_BACKEND = search_backend()
LINKER_PKL, LINKER_META = require_bundle("linker_env", SEARCH_BACKEND)
if SEARCH_BACKEND == "local":
    from src.local_search import LocalBM25Search
    search_client = LocalBM25Search("data/snapshots/chase_2026_05_27/chunks.jsonl")
    print(f"  Backend: local BM25 ({search_client.get_params()['num_chunks']} chunks)")
else:
    import benchmax.config as bmcfg
    from benchmax.rag.corpus.postgres.search import PostgresSearch
    platform_url = bmcfg.platform_url()
    search_client = PostgresSearch(
        corpus_name=CORPUS_NAME,
        base_url=platform_url,
        corpus_id=CORPUS_ID,
        token_provider=resolve_token_provider(platform_key),
    )
    print(f"  Backend: PostgresSearch (Castform)")

print("Building metadata linker...")
metadata_linker = MetadataChunkLinker(
    source=source,
    profile=profile,
    config=MetadataLinkerConfig(),
)

print("Building search-agent linker (pre-built LinkerEnv bundle)...")
linker = SearchAgentLinker(
    metadata_linker=metadata_linker,
    source=source,
    cfg=SearchAgentLinkerCfg(
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
    search_agent_pct=1.0,
    rollout_client=RolloutClient(api_key=platform_key),
    search_client=search_client,
    llm_model="gpt-5.4",
    llm_base_url=llm_url,
    llm_api_key=llm_key,
)
print("  Linker built successfully (using pre-built LinkerEnv bundle)")

# Pick a chunk to test with
test_chunk = None
for c in chunks:
    content = str(getattr(c, "content", c))
    if len(content) >= 500 and "credit card" in content.lower():
        test_chunk = c
        break

if test_chunk is None:
    test_chunk = chunks[0]

content_preview = str(getattr(test_chunk, "content", test_chunk))[:200]
chunk_id = getattr(test_chunk, "hash", "?")
print(f"\nTest chunk: {chunk_id}")
print(f"  Preview: {content_preview}...")

print(f"\nRunning linker.link(target_hop_count=2)...")
t0 = time.time()
bundle = linker.link(test_chunk, target_hop_count=2)
elapsed = time.time() - t0

print(f"\n{'='*60}")
print(f"RESULT  ({elapsed:.1f}s)")
print(f"{'='*60}")
hints = dict(bundle.structural_hints) if bundle.structural_hints else {}
print(f"  secondary_chunks: {len(bundle.secondary_chunks)}")
print(f"  target_hop_count: {bundle.target_hop_count}")
print(f"  confidence: {hints.get('confidence', '?')}")
print(f"  reason: {hints.get('reason', 'n/a')}")
print(f"  linker: {hints.get('linker', '?')}")
print(f"  queries_used: {hints.get('queries_used', [])}")
print(f"  candidates_found: {hints.get('candidates_found', '?')}")
print(f"  evidence_chain: {str(hints.get('evidence_chain', ''))[:200]}")

if bundle.secondary_chunks:
    print(f"\n  Secondary chunks:")
    for i, sc in enumerate(bundle.secondary_chunks):
        sc_content = str(getattr(sc, "content", sc))[:150]
        sc_id = getattr(sc, "hash", "?")
        print(f"    [{i+1}] {sc_id}")
        print(f"        {sc_content}...")
else:
    print(f"\n  No secondary chunks found.")
    if hints.get("reason"):
        print(f"  Reason: {hints['reason']}")

print(f"\nFull structural_hints:")
print(json.dumps({k: str(v)[:200] for k, v in hints.items()}, indent=2))
