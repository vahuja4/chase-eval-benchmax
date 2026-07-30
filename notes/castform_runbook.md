# Castform runbook

How to exercise the Castform (hosted) path now that local is the default.
Background: notes/rollout_interface.md D8-D9.

## Corpus

- Name: `chase_help_2026_05_27`
- corpus_id: `6558ec44-c948-4ed0-a099-63dd786078ad`
- 3,089 chunks / 289 docs (local snapshot:
  `data/snapshots/chase_2026_05_27/chunks.jsonl`)

**corpus_id-only rule:** always pass `corpus_id` explicitly to
`PostgresSearch` / `populate_from_existing_corpus`. Name-based lookup
goes through `get_or_create_corpus`, which silently **creates** an empty
corpus on a typo'd name (`rag/corpus/postgres/search.py:59-64`).

## Required environment (.env)

- `PLATFORM_API_KEY` — Castform platform key. Resolved by the credential
  seam; don't pass it as a literal `token_provider` (it would be baked
  into pickled bundles).
- `LLM_API_KEY` / `LLM_BASE_URL` — OpenAI key for linker rollouts,
  generation, and judge filters (our own key; no Castform LLM credits).
- `ANTHROPIC_API_KEY` — naturalness judge in the run scripts.

## Bundles

Per-backend directories (see bundles/README.md). Note: the directory is
`bundles/postgres/`, keyed 1:1 off `SEARCH_BACKEND=postgres` — the 3a
plan called this `bundles/castform/`; naming follows the env var instead.

Rebuild the Castform set:

    SEARCH_BACKEND=postgres python build_env_bundle.py

(Not needed after every switch — both sets coexist. Rebuild only when
LinkerEnv/SearchEnv config or benchmax version changes. Building the
postgres set needs no network; PostgresSearch pickles lazily.)

## Test commands

    pytest                    # local suite; castform marker deselected
    pytest -m castform        # health check only: one read-only BM25
                              # query proving corpus + auth + API alive
                              # (last verified alive 2026-07-30, 1.3s)

## Running the original pipeline on Castform

    SEARCH_BACKEND=postgres python run_natural_multihop.py

`require_bundle` fails loudly if the postgres bundles are missing or
stamped with the wrong backend. Chunk source + retrieval-too-easy filter
hit Castform unconditionally in *both* modes (Pipeline._load_source
hard-codes PostgresChunkSource); a full linker rollout additionally
consumes one Castform rollout credit per item plus OpenAI calls.
