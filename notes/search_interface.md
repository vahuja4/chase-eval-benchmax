# Search interface (Part A) — SearchEnv / LinkerEnv contract

Read-only investigation. Source read (never edit):
`.../site-packages/benchmax/envs/postgres_search/{search_env.py, linker_env.py}`,
`.../benchmax/rag/corpus/search_client.py`,
`.../benchmax/rag/corpus/postgres/{search.py, client.py, models.py}`.

A local drop-in must preserve the **agent-facing contract** (tool schema,
result text, prompt) and the **`SearchClient` seam** behind it. Swap the
backend freely; keep both boundaries byte-compatible with what's below.

## 1. Search tool schema (what the agent sees)

Two envs expose a tool named **`search`**; both build the schema from
`SearchClient.available_modes`.

### `SearchEnv` (answer/RL env) — `search_env.py:210-241`
- name: `search`; description: `"Search the corpus."`
- input schema properties:
  - `query` — string, `"Search query string."` (**required**)
  - `limit` — integer, `"Max number of results to return (default 10)."`
  - `mode` — **added only if `len(available_modes) > 1`**; string,
    `enum = sorted(available_modes)`, description
    `"Search mode. Available: {modes}. Default: {default_mode}."`
- `required: ["query"]`
- Default mode selection (`__init__`, l.199-208): `hybrid` if available,
  else `lexical`, else `modes[0]`, else `lexical`.
- Handler `_search_tool(query, mode=None, limit=10)` →
  `self._search.search(query=query, mode=mode or default_mode, top_k=limit)`.

### `LinkerEnv` (chunk-linking env — the one used by natural-multihop) — `linker_env.py:129-149`
- name: `search`; description: `"Search the corpus for related content."`
- input schema properties: **`query` (required) and `limit` only —
  NO `mode` parameter, ever.** Mode is hard-wired to `self._default_mode`
  (same hybrid→lexical→modes[0] resolution) inside `_search_tool`
  (l.196-210). The linker agent cannot pick a search mode.
- `max_search_calls` default = **3** (vs SearchEnv default 10).

## Result structure returned to the agent (formatted string, not JSON)

The tool returns a **plain-text block**, one entry per result.

`SearchEnv._format_results` (l.361-394), per result dict
(`content`, `source`, `score`, `metadata`):
```
{i}. — [source: {source}] (score: {score:.2f})
   Metadata: {display_md}          # omitted if empty
   Content: {content}
```
- `source` / score segments omitted when falsy; entries joined by `\n`.
- `display_md` drops keys `content`, `_local_hash`, `chunk_hash`,
  `char_count`, any `_`-prefixed key, and None/empty values.
- Empty results → `"No results found."`
- **Chunk id in output = the `source` field = `metadata["file"]`** (the
  document id, e.g. `p_00108`), NOT the chunk hash. This is the citable id
  the answer agent must echo as `[Source: <id>]`.

`LinkerEnv._format_results` (l.212-226) is terser (no metadata line):
```
{i}. [source: {source}] (score: {score:.2f})
   {content}
```

## 2. SYSTEM_PROMPT_TEMPLATE (SearchEnv, l.112-135)

```
Answer the given question by searching over {corpus_description}.

First, reason about the question inside <think>...</think>. You may want to rephrase the
question or break it down into sub-questions.

Call the search tool to retrieve relevant results. After receiving information, reason
about it inside <think>...</think> before either:
(1) issuing a new search query
(2) providing the final answer

Each reasoning step should be grounded in retrieved information.

You can search up to {max_search_calls} times. Break the question down across multiple
search queries to gather comprehensive information.

Recommended approach:
1. If initial results do not contain the answer, re-query with broadened or rephrased language.
2. Reference retrieved chunks to formulate more specific follow-up queries
(e.g. using keywords in chunk content or using metadata).

When you have gathered enough information, return your final answer inside <answer>...</answer>
tags. Cite your sources inline using [Source: <source_id>] next to each claim.
```
Rendered via `render_system_prompt(corpus_description, max_search_calls)`
using a custom `{name}`-only substituter (`_render_template`, l.50-61) that
leaves JSON-like braces intact.

**Parts coupled to tool behavior / result format:**
- "Call the **search** tool" — the tool name must stay `search`.
- "**keywords in chunk content or using metadata**" — assumes results
  surface both content and a metadata line (the SearchEnv format above).
- Citation contract: **`[Source: <source_id>]`**. Scoring parses this with
  `_CITATION_RE = \[Source:\s*([^\]]+)\]` (case-insensitive, l.41) and
  compares against reference ids drawn from `metadata["file"]`/`file_path`
  (`_extract_reference_ids`, l.497-515). So the `<source_id>` the agent must
  emit == the `source` shown in results == doc-level `file` id. A local
  backend that changes what goes in `source` silently breaks citation recall/
  precision.

(LinkerEnv has its own separate system prompt — evidence-chain builder,
`<evidence_chain>` output, l.22-69 — with reasoning-mode hints for
temporal/inference/sequential. No citation format; not reward-scored.)

## 3. How a search actually executes (the seam we replace)

Both envs call `self._search.search(query, mode, top_k)` where `_search` is a
**`SearchClient`** (Protocol, `search_client.py`): pickle-safe, methods
`search()`, `embed()`, property `available_modes`, `get_params()`.
`search()` must return `list[dict]` with keys **`content`, `source`,
`metadata`, `score`**, ordered by relevance.

Current concrete impl = **`PostgresSearch`** (`postgres/search.py`):
- **Lexical/BM25 only.** `available_modes == ["lexical"]`; `search()` raises
  `ValueError` unless `mode in ("auto","lexical")`. `embed()` returns `None`.
- Delegates to **`CorpusClient`** (`postgres/client.py`) — an HTTP client
  (httpx) against the **Castform Corpora API**, `base_url` (e.g.
  `http://localhost:3000`), bearer resolved per-request via
  `platform_bearer` (token_provider seam).
- Search endpoint: **`POST /v1/corpora/{corpus_id}/search`** with JSON
  `{query, limit, offset, [metadata], [filters]}` → response `{results:[{id,
  content, metadata, score}], total}`. `corpus_id` resolved via
  `get_or_create_corpus(name)` (`GET/POST /v1/corpora`).
- `PostgresSearch.search` maps each API chunk →
  `{content, source: metadata.get("file",""), metadata: dict(metadata),
  score: score or 0.0}`.

**The seam to replace = the `SearchClient` object** (ideally a local
BM25-backed impl exposing the same 4 methods), OR — lower-level — the
`CorpusClient` HTTP endpoints. Replacing at the `SearchClient` level is
cleanest: the two envs, tool schema, prompt, and scoring stay untouched.

## 4. What a local replacement must also reproduce

- **Result dict keys exactly**: `content`, `source`, `metadata`, `score`.
  `source` MUST be the doc-level `file` id (citation + reference-id matching
  depend on it). Preserve `metadata["file"]` (and ideally `file_path`).
- **`available_modes`** drives the tool schema: return `["lexical"]` to keep
  the current no-`mode`-param SearchEnv schema and the linker's fixed-mode
  behavior. Returning >1 mode would add a `mode` enum param to SearchEnv's
  tool and change the agent's affordances.
- **top_k / limit**: default 10 (both envs pass `limit`, default 10; agent
  may override).
- **Truncation**: SearchEnv caps tool output at **10000 chars** with suffix
  `"\n...[truncated due to character limit]"` (l.87-88, 396-405); LinkerEnv
  caps at **8000** with `"\n...[truncated]"` (l.19-20). These live in the env,
  not the client — a backend swap keeps them, but total content volume
  affects where truncation bites.
- **Error format**: `_search_tool` catches all exceptions and returns the
  string `f"Error:\n{traceback.format_exc()}"` to the agent (never raises).
  Empty query → `"Error: Missing required parameter: 'query'"`. Unknown tool
  → `"Error: Unknown tool '{name}'"`. A local client should raise on failure
  (the env formats it), and must raise `ValueError` for unsupported modes to
  match PostgresSearch semantics.
- **Metadata display filtering** (SearchEnv): keys `content`, `_local_hash`,
  `chunk_hash`, `char_count`, `_`-prefixed, and empty values are hidden from
  the agent — keep other metadata (headings, file, dates) present so the
  prompt's "using metadata" guidance still works.
- **pickle-safety**: `SearchClient` impls must survive cloudpickle (store
  only serializable params; lazily build clients — see `__getstate__`/
  `__setstate__` in PostgresSearch) if remote rollout is ever reinstated.
