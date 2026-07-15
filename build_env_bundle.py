"""
Step 3 — Build the env bundle for the env_rollout filter (BM25 / Postgres route).

IMPORTANT: run this with benchmax PIP-INSTALLED (uv pip install "benchmax[rag]"),
NOT from a source checkout / PYTHONPATH. The bundler pickles installed packages
BY REFERENCE; if benchmax looks "local" it gets pickled BY VALUE and cloudpickle
walks the live module graph and fails on a thread lock. Verify before running:
    python -c "import importlib.metadata as m; print(m.version('benchmax'))"


What this produces:
  env_cls.pkl       <- cloudpickle of (MyChaseSearchEnv, constructor_args)
  env_metadata.json <- bundle metadata stamp

These two files are referenced in config.yaml under:
  filtering.env_rollout.env_bundle.env_cls_file / env_metadata_file

Why this is the "simple route":
  - PostgresSearch only needs corpus_name + base_url; its token resolves lazily
    via the credential seam (platform_bearer) INSIDE Castform's rollout. Nothing
    machine-local is pickled, so the env reconstructs cleanly on Castform infra.
  - BM25/lexical only — matches the eval's retrieval regime (conservative oracle).
"""

from typing import Any

from benchmax.bundle import dump_bundle
from benchmax.envs.postgres_search.search_env import SearchEnv
from benchmax.envs.example_id import make_example
from benchmax.envs.types import Example
from benchmax.rag.corpus.postgres.search import PostgresSearch
from benchmax import config

# ----------------------------------------------------------------------------
# FILL THESE IN
# ----------------------------------------------------------------------------
CORPUS_NAME = "chase_help_2026_05_27"   # same name used at upload (Step 2)
CORPUS_DESCRIPTION = "Chase.com public help and product articles"  # one line, shown to the agent
MAX_SEARCH_CALLS = 8                             # each call is one BM25 query

# Your own LLM endpoint for the in-env judge (correctness scoring during rollout).
# Keep this OFF Castform's proxy so your $50 isn't spent on judge tokens.
JUDGE_BASE_URL = "https://api.openai.com/v1"
JUDGE_MODEL = "gpt-5.4"
# NOTE: do not hardcode the judge API key here. SearchEnv resolves the judge
# credential at call time via judge_token_provider. For a non-Castform judge URL
# you pass the key through the rollout/env credential path, not baked into the pickle.
# ----------------------------------------------------------------------------


# Subclass SearchEnv and render its system prompt at class-definition time
# (the prompt is a static class attribute the rollout reads via cls).
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


# The SearchClient the agent's `search` tool calls. Two strings only — token is
# resolved remotely via the credential seam. This is what makes BM25 the clean path.
search_client = PostgresSearch(
    corpus_name=CORPUS_NAME,
    base_url=config.platform_url(),
)

# constructor_args are pickled alongside the class and used to build the env on
# the far side: env_class(search=<client>, judge_base_url=..., judge_model=..., ...)
constructor_args = {
    "search": search_client,
    "judge_base_url": JUDGE_BASE_URL,
    "judge_model": JUDGE_MODEL,
    "max_search_calls": MAX_SEARCH_CALLS,
    # Reward weights only matter for TRAINING rollouts; the env_rollout FILTER
    # uses an equivalence judge + tool-call count, not these. Defaults are fine.
}

bundle = dump_bundle(
    MyChaseSearchEnv,
    constructor_args=constructor_args,
    pip_dependencies=["benchmax"],
)

with open("env_cls.pkl", "wb") as f:
    f.write(bundle.pickled)

with open("env_metadata.json", "wb") as f:
    f.write(bundle.metadata.to_json_bytes())

print("Wrote env_cls.pkl and env_metadata.json")
print("Corpus:", CORPUS_NAME, "| modes: lexical (BM25) | max_search_calls:", MAX_SEARCH_CALLS)
