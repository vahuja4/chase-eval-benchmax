# Linker search-mode usage (Part B)

Read-only tally across the natural-multihop / retrieval-filtered runs, plus a
source check of what modes the linker actually exposes.

## Bottom line

**The linker agent used lexical (BM25 keyword) search 100% of the time —
because that is the only mode it was ever offered.** There is no
keyword-vs-semantic-vs-hybrid choice in the linker at all. This settles the
open fork in CLAUDE.md toward **BM25-only** for the local backend (from the
linker's perspective).

## Source evidence — the linker exposes exactly one, fixed mode

`benchmax/envs/postgres_search/linker_env.py` (the natural-multihop linker
env, `SearchAgentLinker` backend):
- The `search` tool schema has **only `query` and `limit`** (l.129-146). There
  is **no `mode` parameter** — the agent physically cannot request semantic or
  hybrid search.
- `_search_tool` calls `self._search.search(query, mode=self._default_mode,
  top_k=limit)` (l.196-210). Mode is fixed at construction, not agent-chosen.
- `_default_mode` resolves `hybrid → lexical → modes[0] → lexical` from
  `search.available_modes` (l.119-127). With the current backend
  `PostgresSearch.available_modes == ["lexical"]`, so **default_mode =
  "lexical"** on every run.

So the mode is **not agent-configurable**, and given the lexical-only backend
it is also **not effectively configurable at all** without swapping the
`SearchClient`. (Even `SearchEnv` — the answer env — only surfaces a `mode`
enum when `len(available_modes) > 1`, which never happened here.)

## Data evidence — no mode field is recorded, only query strings

Tallied `step_2_linking_details.json` across:
`outputs/natural_multihop/` (21), `outputs/natural_multihop_batch4/` (35),
`outputs/retrieval_filtered_batch3/` (22). *(batch5 has no
step_2_linking_details.json — only eval/train jsonl.)*

- Linker backends seen: `search_agent` (29 records) and `search_agent_v2`
  (49 records).
- **No `mode` / `search_mode` key exists anywhere** in any record — searched
  the full nested structure. The linker records `queries_used` (query strings
  only), never a mode.
- `queries_used` present on the 49 `search_agent_v2` records; query-count
  distribution: 1 query ×17, 2 ×5, 3 ×26, 4 ×1 → **109 total search queries**,
  all necessarily lexical/BM25.
- The 29 `search_agent` (v1) records logged `reason: "no_queries"`,
  `confidence: 0.0` — they produced no usable queries (no linking), so 0
  searches contributed.

### Not to be confused: `reasoning_mode`
Records carry a `reasoning_mode` field (`factual` ×16, `inference` ×8, `""`
×74). This is the **multi-hop reasoning type** (drives `_REASONING_MODE_HINTS`
in the prompt: temporal / inference / sequential), **not** a search mode. It
changes prompt wording, not how retrieval runs. (Note `factual` isn't a key in
`_REASONING_MODE_HINTS`, so it yields an empty hint.)

## Tally summary

| dimension | value |
|---|---|
| keyword / lexical (BM25) | **100%** (109/109 queries; only mode offered) |
| semantic (vector) | 0 — not exposed, backend can't do it |
| hybrid | 0 — not exposed, backend can't do it |
| mode agent-selectable? | **No** (LinkerEnv `search` tool has no `mode` param) |

## Implication for the open fork (BM25-only vs BM25 + embeddings)

For **linking**, BM25-only fully reproduces observed behavior — the agent
never had another mode. Adding an embedding index would be a *new capability*,
not parity with the Castform runs. If embeddings are added later, note it
would require either (a) a `SearchClient` reporting >1 mode **and** editing
`LinkerEnv` to expose a `mode` param (currently absent), or (b) simply making
`_default_mode` hybrid — which would silently change linker retrieval vs the
baseline, so any such change must be validated by diffing per-item linking
verdicts against the baseline outputs.
