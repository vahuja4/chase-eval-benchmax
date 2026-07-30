"""
Build env bundles for the env_rollout filter (SearchEnv) AND the
search-agent linker (LinkerEnv).

Produces, under bundles/{SEARCH_BACKEND}/:
  env_cls.pkl            + env_metadata.json            (answer/RL env)
  linker_env_cls.pkl     + linker_env_metadata.json     (linker env)

The search backend is selected via SEARCH_BACKEND env var:
  local    (default) — LocalBM25Search over local chunks.jsonl
  postgres            — PostgresSearch via Castform Corpora API

Each backend writes to its own directory, so both bundle sets coexist —
build each once and switch freely via SEARCH_BACKEND. The run scripts
resolve the same variable through src.bundles.require_bundle().

IMPORTANT: run this with benchmax PIP-INSTALLED (uv pip install "benchmax[rag]"),
NOT from a source checkout / PYTHONPATH. The bundler pickles installed packages
BY REFERENCE; if benchmax looks "local" it gets pickled BY VALUE and cloudpickle
walks the live module graph and fails on a thread lock. Verify before running:
    python -c "import importlib.metadata as m; print(m.version('benchmax'))"
"""

import importlib.metadata
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

from src.bundles import bundle_dir, search_backend

# Pin the exact installed version. An unpinned "benchmax" is unsatisfiable on
# Castform workers: PyPI stable releases are yanked and the worker's resolver
# won't opt into pre-releases without an explicit ==dev pin (see
# notes/known_issues.md #5).
BENCHMAX_PIN = f"benchmax=={importlib.metadata.version('benchmax')}"

SEARCH_BACKEND = search_backend()
BUNDLE_DIR = bundle_dir(SEARCH_BACKEND)
BUNDLE_DIR.mkdir(parents=True, exist_ok=True)

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
    pip_dependencies=[BENCHMAX_PIN],
)

with open(BUNDLE_DIR / "env_cls.pkl", "wb") as f:
    f.write(search_bundle.pickled)

meta_bytes = search_bundle.metadata.to_json_bytes()
meta_dict = json.loads(meta_bytes)
meta_dict["search_backend"] = SEARCH_BACKEND
with open(BUNDLE_DIR / "env_metadata.json", "w") as f:
    json.dump(meta_dict, f, indent=2)

print(f"Wrote {BUNDLE_DIR}/env_cls.pkl + env_metadata.json (SearchEnv, backend={SEARCH_BACKEND})")


# ---- Linker env (LinkerEnv) bundle ----

linker_env_args = {
    "search": search_client,
    "max_search_calls": LINKER_MAX_SEARCH_CALLS,
}

linker_bundle = dump_bundle(
    LinkerEnv,
    constructor_args=linker_env_args,
    pip_dependencies=[BENCHMAX_PIN],
)

with open(BUNDLE_DIR / "linker_env_cls.pkl", "wb") as f:
    f.write(linker_bundle.pickled)

linker_meta_bytes = linker_bundle.metadata.to_json_bytes()
linker_meta_dict = json.loads(linker_meta_bytes)
linker_meta_dict["search_backend"] = SEARCH_BACKEND
with open(BUNDLE_DIR / "linker_env_metadata.json", "w") as f:
    json.dump(linker_meta_dict, f, indent=2)

print(f"Wrote {BUNDLE_DIR}/linker_env_cls.pkl + linker_env_metadata.json (LinkerEnv, backend={SEARCH_BACKEND})")
print(f"Corpus: {CORPUS_NAME} | modes: lexical (BM25) | search_calls: {MAX_SEARCH_CALLS} / {LINKER_MAX_SEARCH_CALLS}")
