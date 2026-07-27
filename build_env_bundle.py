"""
Build env bundles for the env_rollout filter (SearchEnv) AND the
search-agent linker (LinkerEnv).

Produces:
  env_cls.pkl            + env_metadata.json            (answer/RL env)
  linker_env_cls.pkl     + linker_env_metadata.json     (linker env)

The search backend is selected via SEARCH_BACKEND env var:
  local    (default) — LocalBM25Search over local chunks.jsonl
  postgres            — PostgresSearch via Castform Corpora API

After switching backends, re-run this script to regenerate all four
bundle files. The run scripts consume these pickles directly.

IMPORTANT: run this with benchmax PIP-INSTALLED (uv pip install "benchmax[rag]"),
NOT from a source checkout / PYTHONPATH. The bundler pickles installed packages
BY REFERENCE; if benchmax looks "local" it gets pickled BY VALUE and cloudpickle
walks the live module graph and fails on a thread lock. Verify before running:
    python -c "import importlib.metadata as m; print(m.version('benchmax'))"
"""

import json
import os
from typing import Any

from benchmax.bundle import dump_bundle
from benchmax.envs.postgres_search.search_env import SearchEnv
from benchmax.envs.postgres_search.linker_env import LinkerEnv
from benchmax.envs.example_id import make_example
from benchmax.envs.types import Example
from benchmax import config

# ----------------------------------------------------------------------------
# FILL THESE IN
# ----------------------------------------------------------------------------
CORPUS_NAME = "chase_help_2026_05_27"
CORPUS_DESCRIPTION = "Chase.com public help and product articles"
MAX_SEARCH_CALLS = 8
LINKER_MAX_SEARCH_CALLS = 3
CHUNKS_PATH = "data/snapshots/chase_2026_05_27/chunks.jsonl"

JUDGE_BASE_URL = "https://api.openai.com/v1"
JUDGE_MODEL = "gpt-5.4"
# ----------------------------------------------------------------------------

SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "local")

if SEARCH_BACKEND == "local":
    from src.local_search import LocalBM25Search
    search_client = LocalBM25Search(CHUNKS_PATH)
    print(f"Backend: local BM25 ({search_client.get_params()['num_chunks']} chunks)")
else:
    from benchmax.rag.corpus.postgres.search import PostgresSearch
    search_client = PostgresSearch(
        corpus_name=CORPUS_NAME,
        base_url=config.platform_url(),
    )
    print(f"Backend: PostgresSearch (Castform)")


# ---- Answer/RL env (SearchEnv) bundle ----

class MyChaseSearchEnv(SearchEnv):
    system_prompt = SearchEnv.render_system_prompt(
        corpus_description=CORPUS_DESCRIPTION,
        max_search_calls=MAX_SEARCH_CALLS,
    )

    @classmethod
    def dataset_preprocess(cls, example: Any, **kwargs) -> Example:
        question = example.get("question") or example.get("prompt") or ""
        return make_example(
            prompt_messages=[{"role": "user", "content": question}],
            task={
                "question": question,
                "ground_truth": example.get("answer"),
                "reference_chunks": example.get("reference_chunks", []),
            },
            system_prompt=cls.system_prompt,
        )


search_env_args = {
    "search": search_client,
    "judge_base_url": JUDGE_BASE_URL,
    "judge_model": JUDGE_MODEL,
    "max_search_calls": MAX_SEARCH_CALLS,
}

search_bundle = dump_bundle(
    MyChaseSearchEnv,
    constructor_args=search_env_args,
    pip_dependencies=["benchmax"],
)

with open("env_cls.pkl", "wb") as f:
    f.write(search_bundle.pickled)

meta_bytes = search_bundle.metadata.to_json_bytes()
meta_dict = json.loads(meta_bytes)
meta_dict["search_backend"] = SEARCH_BACKEND
with open("env_metadata.json", "w") as f:
    json.dump(meta_dict, f, indent=2)

print(f"Wrote env_cls.pkl + env_metadata.json (SearchEnv, backend={SEARCH_BACKEND})")


# ---- Linker env (LinkerEnv) bundle ----

linker_env_args = {
    "search": search_client,
    "max_search_calls": LINKER_MAX_SEARCH_CALLS,
}

linker_bundle = dump_bundle(
    LinkerEnv,
    constructor_args=linker_env_args,
    pip_dependencies=["benchmax"],
)

with open("linker_env_cls.pkl", "wb") as f:
    f.write(linker_bundle.pickled)

linker_meta_bytes = linker_bundle.metadata.to_json_bytes()
linker_meta_dict = json.loads(linker_meta_bytes)
linker_meta_dict["search_backend"] = SEARCH_BACKEND
with open("linker_env_metadata.json", "w") as f:
    json.dump(linker_meta_dict, f, indent=2)

print(f"Wrote linker_env_cls.pkl + linker_env_metadata.json (LinkerEnv, backend={SEARCH_BACKEND})")
print(f"Corpus: {CORPUS_NAME} | modes: lexical (BM25) | search_calls: {MAX_SEARCH_CALLS} / {LINKER_MAX_SEARCH_CALLS}")
