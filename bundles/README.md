# Env bundles, per search backend

One directory per `SEARCH_BACKEND` value — `local/` (LocalBM25Search) and
`postgres/` (Castform Corpora API) — each holding `env_cls.pkl`,
`env_metadata.json`, `linker_env_cls.pkl`, `linker_env_metadata.json`, so
switching backends never clobbers the other set. Build with
`SEARCH_BACKEND=<backend> python build_env_bundle.py`; resolve paths via
`src.bundles.require_bundle()` (verifies the `search_backend` metadata
stamp). Pickles are gitignored; metadata JSONs are tracked.
