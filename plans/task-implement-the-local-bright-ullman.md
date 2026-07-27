# Plan: Local BM25 Search Backend

## Status: Implemented

All three deliverables are complete. 20/20 tests pass. Replay parity:
100% hit rate (70/70 secondary doc ids found in local top-10), average
rank 3.6. Text-only indexing sufficient — no need for the
text+title+heading fallback.

Remaining: smoke test (`SEARCH_BACKEND=local python test_linker.py`).

## Context

The project is migrating off Castform's hosted platform. Currently,
corpus search is handled by `PostgresSearch` — an HTTP client that
calls Castform's Corpora API for BM25 retrieval. Since the linker
agent used lexical search 100% of the time (109/109 queries; see
`notes/linker_search_modes.md`), the local replacement is BM25-only.

The local backend must satisfy the `SearchClient` protocol exactly
(same method signatures, same result dict keys, same mode semantics)
so that both env classes (`LinkerEnv`, `SearchEnv`) and all
downstream scoring/citation logic remain untouched.

---

## Deliverable 1: `src/local_search.py` — LocalBM25Search

### Constructor

```python
class LocalBM25Search:
    def __init__(self, chunks_path: str | Path, *, k1: float = 1.5, b: float = 0.75):
```

- Load `chunks.jsonl` line-by-line, parse each JSON object.
- Build the `bm25s.BM25(k1=k1, b=b)` index over the `text` field only
  (provisional choice — see note below).
- Tokenization: `bm25s.tokenize(texts, stemmer=stemmer)` using
  PyStemmer's Snowball English stemmer. **Why**: PostgreSQL's
  `tsvector` uses Snowball stemming for English; this gives the
  closest parity without trying to replicate Castform's exact
  pipeline. bm25s handles lowercasing and splitting; Snowball handles
  morphological normalization.
- Store the parsed chunk dicts in a list (indexed parallel to BM25
  corpus) for result construction.

### `search(query, mode="auto", top_k=10) → list[dict]`

- Validate mode: `mode not in ("auto", "lexical")` → `raise ValueError`.
- Tokenize query with same stemmer, call `retriever.retrieve(q_tokens, k=top_k)`.
- Build result dicts with exactly these keys:
  - `content`: chunk `text`
  - `source`: chunk `parent_page_id` (e.g. `"p_00108"`)
  - `metadata`: lean allowlist of exactly 6 keys:
    `file` (= `parent_page_id`), `chunk_id`, `page_title`,
    `heading_path` (array joined with `" > "`), `stratum`,
    `sub_stratum`. Do NOT pass through `content_hash`,
    `info_density`, `parent_page_ids`, `occurrence_count`,
    or boilerplate flags — SearchEnv's display filter wouldn't
    hide them, and they'd leak into agent context.
  - `score`: float from bm25s
- **Critical invariant**: `source == metadata["file"]`.
- Return results ordered by descending score.
- Empty results → return `[]`.

### Other protocol methods

- `available_modes` (property): returns `["lexical"]`
- `embed(text)`: returns `None`
- `get_params()`: returns `{"k1": k1, "b": b, "stemmer": "snowball_english", "chunks_path": str(chunks_path), "num_chunks": len(self._chunks)}`

### Pickle support (hard requirement — see Deliverable 2)

- `__getstate__`: return `{"chunks_path": ..., "k1": ..., "b": ...}`
- `__setstate__`: store params; set `_index = None`, `_chunks = None`
- `_ensure_index()`: lazy rebuild from `chunks_path` if `_index is None`.
  Called at the top of `search()`, `available_modes`, `get_params()`.

### File structure

```
src/
  __init__.py          (empty)
  local_search.py      (LocalBM25Search)
```

**Provisional: text-only indexing.** The BM25 index covers only the
chunk `text` field. If replay parity turns out weak, compare against
indexing `text + page_title + heading_path` concatenated. The known-
answer queries have been verified to work with text-only.

Dependencies to install: `bm25s`, `PyStemmer`

---

## Deliverable 2: Wiring

### Architecture finding: bundle-only (no direct env instance)

`SearchAgentLinkerCfg` has only `env_bundle: EnvBundleConfig`, which
deals with serialized pickle files/paths. There is no way to pass a
constructed env instance directly.

`SearchAgentLinker._prepare_env_bundle(search_client)` (line 118-135)
has two paths:
1. **Pre-built bundles** (`env_bundle.has_paths()` or `.has_files()`):
   returns immediately — the `search_client` parameter is **unused**.
2. **Inline bundling**: calls `dump_bundle(LinkerEnv, constructor_args={"search": search_client})`
   — pickles the search_client.

The current run scripts always provide pre-built bundle files, so the
`search_client` passed to `SearchAgentLinker.__init__` is effectively
dead. To actually use LocalBM25Search in the linker, you must either
(a) rebuild the bundle pickle files via `build_env_bundle.py`, or
(b) remove the env_bundle config and let `_prepare_env_bundle` pickle
LocalBM25Search inline.

**Implication**: `LocalBM25Search.__getstate__/__setstate__` is a hard
requirement — the search client always gets pickled, either at
bundle-build time or inline by the pipeline.

### Backend switch: `SEARCH_BACKEND` env var (default `"local"`)

#### `test_linker.py` (lines 42–47)

Replace the `PostgresSearch` construction block with:

```python
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "local")
if SEARCH_BACKEND == "local":
    from src.local_search import LocalBM25Search
    search_client = LocalBM25Search("data/snapshots/chase_2026_05_27/chunks.jsonl")
    print(f"  Backend: local BM25 ({search_client.get_params()['num_chunks']} chunks)")
else:
    from benchmax.rag.corpus.postgres.search import PostgresSearch
    search_client = PostgresSearch(
        corpus_name=CORPUS_NAME, base_url=platform_url,
        corpus_id=CORPUS_ID, token_provider=resolve_token_provider(platform_key),
    )
    print(f"  Backend: PostgresSearch (Castform)")
```

Note: with the pre-built env_bundle, the search_client is unused by
the linker bundler — but switching it is still correct preparation for
when the pre-built bundle is dropped.

#### `build_env_bundle.py` — rewrite to produce BOTH bundles

The original script only builds `env_cls.pkl` (the answer/SearchEnv
bundle). But the run scripts consume `linker_env_cls.pkl` (the
LinkerEnv bundle) — and nothing in the repo was building it. Extend
the builder to produce both:

1. **`env_cls.pkl` + `env_metadata.json`** — SearchEnv bundle
   (answer env, used by rollout scoring).
2. **`linker_env_cls.pkl` + `linker_env_metadata.json`** — LinkerEnv
   bundle with `{"search": search_client, "max_search_calls": 3}`.

Backend switch via `SEARCH_BACKEND` env var (default `"local"`):

```python
SEARCH_BACKEND = os.environ.get("SEARCH_BACKEND", "local")
if SEARCH_BACKEND == "local":
    from src.local_search import LocalBM25Search
    search_client = LocalBM25Search("data/snapshots/chase_2026_05_27/chunks.jsonl")
else:
    search_client = PostgresSearch(corpus_name=CORPUS_NAME, base_url=config.platform_url())
```

Stamp `search_backend` into both metadata JSON files so the active
backend is traceable.

#### Run scripts (no direct changes)

`run_natural_multihop.py` and `run_natural_multihop_batch5.py` consume
pre-built pickle bundles. After switching `build_env_bundle.py` to
local, re-run it to regenerate `env_cls.pkl` / `env_metadata.json`.
The run scripts pick up the new backend automatically.

Add a comment at the top of each run script noting this dependency:
```python
# NOTE: Search backend is baked into linker_env_cls.pkl / env_cls.pkl.
# To switch backends, set SEARCH_BACKEND=local|postgres and re-run
# build_env_bundle.py.
```

---

## Deliverable 3: `tests/test_local_search.py`

### 3a. Contract tests

- Result dict keys are exactly `{"content", "source", "metadata", "score"}`
- `source == metadata["file"]` for every result
- `ValueError` raised on `mode="semantic"`
- `available_modes == ["lexical"]`
- `mode="auto"` and `mode="lexical"` both succeed
- Results in descending score order
- Query with no matches returns `[]` (or results — no crash)
- `embed()` returns `None`
- `get_params()` returns dict with keys `k1`, `b`, `stemmer`, `chunks_path`, `num_chunks`

### 3b. Known-answer tests (5 queries)

Each asserts the target `parent_page_id` appears in top-5 results'
`source` field. **Will re-verify after installing bm25s** since the
implementation indexes chunk text only (not page_title + heading_path).

| # | Query | Expected doc | Page title |
|---|-------|-------------|------------|
| 1 | `"Chase Sapphire Reserve annual fee travel credit"` | `p_00209` | The Chase Sapphire Reserve $300 Travel Credit: How it works |
| 2 | `"jumbo loan qualification requirements limits"` | `p_00296` | Qualifying For A Jumbo Loan: Limits and Requirements |
| 3 | `"Chase Ultimate Rewards how the program works"` | `p_00121` | Chase Ultimate Rewards: How Our Program Works |
| 4 | `"Freedom Rise credit limit increase after six months"` | `p_00116` | Freedom Rise Credit Limit Increase |
| 5 | `"what is a joint high yield savings account"` | `p_00054` | What is a joint high-yield savings account? |

If any query fails with text-only indexing, I will adjust the query
wording (not the index) before finalizing.

### 3c. Replay parity (reported, not asserted)

1. Load all 3 `step_2_linking_details.json` files (109 total queries).
2. For each entry with `queries_used`:
   - Replay each query against LocalBM25Search (top_k=10).
   - Collect the returned `source` (doc id) set.
   - Compare against the secondary chunks' `metadata["file"]` from
     the original run.
3. Metrics: per-query hit rate (did original secondary doc ids appear
   in local top-10), aggregate hit rate, average rank when found.
4. Write to `notes/local_search_parity.md`.
5. This is a fidelity measurement — no param tuning, no assertions.
6. **Baseline caveat**: note in the report that the baseline secondary
   selections are post-filtered (400-char minimum, same-file
   exclusion, dedup, Jaccard coherence >= 0.15, diversity cap).
   Hit-rate understates raw retrieval parity — a miss may mean the
   local index retrieved the doc but the linker's downstream filters
   excluded it.
7. Note text-only indexing as provisional; if parity is weak, compare
   against text + page_title + heading_path.

---

## Verification

1. `pip install bm25s PyStemmer` in the venv
2. Re-verify the 5 known-answer queries rank correctly with text-only
   indexing; adjust query wording if needed
3. `pytest tests/test_local_search.py -v` — all contract and
   known-answer tests pass
4. Run replay parity, inspect `notes/local_search_parity.md`
5. Smoke test: `SEARCH_BACKEND=local python test_linker.py` — confirm
   search_client construction succeeds and basic search works (full
   linker test requires Castform rollout, so expect failure downstream)
