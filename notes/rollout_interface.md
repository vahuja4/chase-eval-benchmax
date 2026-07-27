# Rollout interface — local runner design investigation

Read-only investigation. Maps everything a local rollout runner must
replicate to replace Castform's remote rollout service, while keeping
the Castform path selectable side-by-side.

All benchmax citations reference
`/Users/vishal/miniconda3/lib/python3.12/site-packages/benchmax/`.

Re-verified against source 2026-07-27: all line citations checked;
corrections in this pass — (a) our runs use Form-2 file bundles, not
the in-memory Form 3 (A1); (b) Pipeline has no linker-client seam,
`rollout_client_factory` feeds only the env_rollout filter (A3);
(c) LinkerEnv's `max_search_calls` is dead config, not prompt-rendered
(C7); (d) env interface methods are async (C6); (e) name-based
PostgresSearch health checks can create a corpus — use `corpus_id` (D9).

---

## Part A — The client seam

### A1. Where SearchAgentLinker invokes the rollout

**File:** `rag/qa_generation/search_agent_linker.py`

`SearchAgentLinker.__init__` (l.87-113) takes `rollout_client: RolloutClient`
as a constructor arg (l.94) and stores it as `self._rollout_client` (l.104).

The rollout is invoked via `_run_rollout()` (l.277-315), called from
`_link_with_llm()` (l.184-275, specifically l.201).

#### What is sent

`_run_rollout()` builds a kwargs dict and calls
`self._rollout_client.stream_rollout(**kwargs)` at l.315. The kwargs:

```python
kwargs = {
    "raw_example": {                        # built at l.195-199
        "prompt": content[:4000],           # primary chunk text, truncated
        "target_n": n_secondaries,          # int, typically 1 (for 2-hop)
        "reasoning_mode": reasoning_mode,   # str: "", "temporal", "inference", "sequential"
    },
    "llm_model": self._llm_model,           # str, e.g. "gpt-5.4"
    "llm_base_url": self._llm_base_url,     # str, e.g. "https://api.openai.com/v1"
    "llm_api_key": self._llm_api_key,       # str
    "max_turns": max_turns,                 # int, default 4 (auto-scaled to max(4, hop+1))
    "max_tool_calls": max_tool_calls,       # int, default 4 (auto-scaled to max(4, hop))
    "max_completion_tokens": 3072,          # int (from cfg.max_completion_tokens)
    "capture_messages": True,               # always True for linker
    "include_event_meta": False,            # always False for linker

    # Env bundle — one of three forms (l.304-313):
    # Form 1: blob paths (uploaded to Castform storage)
    "env_cls_path": ...,
    "env_metadata_path": ...,
    # Form 2: local files read as bytes via env_bundle.as_bytes_bundle()
    "env_cls_bytes": ...,
    "env_metadata_bytes": ...,
    # Form 3: in-memory bytes from _prepare_env_bundle (fallback when no
    # bundle is pre-configured)
    "env_cls_bytes": self._env_cls_bytes,
    "env_metadata_bytes": self._env_meta_bytes,
}
```

**Which form our runs actually use: Form 2.** All run scripts and
`test_linker.py` set `EnvBundleConfig(env_cls_file=..., env_metadata_file=...)`
(e.g. `run_natural_multihop.py:209-212`, `test_linker.py:72-75`), so
`env_bundle.has_files()` is true and `_prepare_env_bundle()` returns early
(`search_agent_linker.py:125-127`) without ever dumping a bundle. The
search backend that runs is therefore whatever was baked into
`linker_env_cls.pkl` by `build_env_bundle.py` — the `search_client`
constructor arg passed to `SearchAgentLinker` is unused in this
configuration. Form 3 (in-memory `dump_bundle(LinkerEnv,
local_modules=[benchmax], constructor_args={"search": search_client})`,
l.129-135) only fires when no bundle paths/files are configured.

Budget is computed dynamically (l.286-290):
```python
max_turns = cfg.max_turns          # default 4
max_tool_calls = cfg.max_tool_calls  # default 4
if cfg.auto_scale_turns:
    max_turns = max(max_turns, hop_count + 1)
    max_tool_calls = max(max_tool_calls, hop_count)
```

#### RolloutClient.stream_rollout HTTP payload

`platform/client.py:829-848` (signature); payload built at l.910-925 and
POSTed to `{server_url}/v1/rollout/stream` (l.929):

```python
payload = {
    "standardized_example": None,
    "raw_example": raw_example,               # the dict above
    "env": {
        # EITHER blob paths:
        "env_cls_path": str,
        "env_metadata_path": str,
        # OR base64-encoded bytes:
        "env_cls_bytes": base64_str,
        "env_metadata_bytes": base64_str,
    },
    "llm": {
        "base_url": resolved_llm_url,
        "api_key": llm_api_key,
        "model": llm_model,
        "api-version": "",
    },
    "options": {
        "max_turns": max_turns,
        "max_tool_calls": max_tool_calls,
        "max_completion_tokens": max_completion_tokens,
    },
}
```

Auth: `Authorization: Bearer {platform_bearer}` header (l.930), bearer
resolved per request via `self._token_provider()` (l.892).

**LLM key guard** (l.898-908): if `llm_api_key` is empty and
`llm_base_url` equals the platform's own LLM endpoint, the platform
bearer is forwarded as the LLM key; if it points at a third-party host,
`ValueError` is raised. The linker always passes an explicit
`llm_api_key`, so this guard never fires in our runs — but a local
runner that mimics the signature should not replicate the
bearer-forwarding branch (there is no bearer).

### A2. What comes back — rollout result structure

`stream_rollout` (l.829-1001) reads an SSE stream via `_iter_sse`
(l.539). Events have the shape `{"event": str, ...}` where `event` is
one of (terminal set `_TERMINAL` at l.773; per-event fields per
`_print_event`, l.643-740):
- `"rollout_started"` — no useful payload
- `"message"` — carries `{"message": {role, content}}` (l.964-967)
- `"reward"` — carries `{"rewards": ...}` (l.725)
- `"rollout_completed"` — terminal; carries `{"success": bool, "rewards": ..., "error": str|None}`
- `"worker_error"`, `"error"`, `"cancelled"` — terminal error events

**Error behavior** (matters because `link()` catches ANY exception and
falls back to metadata — see B4):
- Non-200 HTTP → typed exceptions (l.939-952): `AuthenticationError`
  (401/403), `RolloutNotFound` (404), `RolloutServerError` (5xx),
  `RolloutError` (other).
- Stream ends without a terminal event, or read timeout/disconnect →
  `RolloutStreamError` (l.971-985).
- A local runner should likewise raise on failure rather than return a
  partial dict — an exception cleanly triggers the metadata fallback,
  while a malformed return propagates as `no_queries`.

When `capture_messages=True` (always for linker), the return dict is
augmented:

```python
{
    "event": "rollout_completed",
    "success": True,
    "rewards": {...},
    "error": None,

    # Added by capture_messages:
    "messages": [...],              # list[dict] — ALL streamed messages
    "assistant_messages": [...],    # assistant-role subset
    "final_assistant_text": "...",  # text from last assistant message
}
```

#### Message format

Content can be:

1. **Structured (list of blocks)** — Anthropic-style tool_use blocks:
   ```python
   {"role": "assistant", "content": [
       {"type": "text", "text": "..."},
       {"type": "tool_use", "name": "search", "id": "call_1",
        "input": {"query": "...", "limit": 10}},
   ]}
   ```

2. **Text string with `<tool_call>` XML** — Hermes/Qwen-style:
   ```python
   {"role": "assistant", "content": "<tool_call>\n{\"name\": \"search\", \"arguments\": {\"query\": \"...\"}}\n</tool_call>"}
   ```

3. **Tool results** appear as blocks in content lists:
   ```python
   {"type": "tool_result", "content": "1. [source: ...] (score: 0.82)\n   ..."}
   ```

The linker's parsers handle both formats (see Part B).

### A3. The swap point

**The swap point is the `rollout_client` constructor argument** of
`SearchAgentLinker.__init__()` (l.87, param at l.94).

- `rollout_client` is **injected**, not constructed internally.
- In the pipeline, it's built by `_build_rollout_client(cfg)`
  (`pipeline.py:183-184`) which constructs
  `RolloutClient(api_key=cfg.platform.api_key)`.
- In `test_linker.py`, it's constructed directly at l.78:
  `RolloutClient(api_key=platform_key)`.

#### ⚠ No Pipeline-level seam for the linker's client

`Pipeline` accepts a `rollout_client_factory` kwarg
(`pipeline.py:1280`, stored l.1284) — but it is threaded **only into
the filter chain** (l.1600 → `_build_filter_chain` l.367 →
`_build_filter_from_stage_name` l.311), where it feeds the
`env_rollout` filter exclusively (l.349-360). The linker builder
`_build_linker` (l.214) hard-codes both:
- `rollout_client=_build_rollout_client(cfg)` at l.274, and
- `search_client=PostgresSearch(...)` at l.261-267.

So going through `Pipeline` with `linker.type == "search_agent"`
always constructs a Castform `RolloutClient` + `PostgresSearch` for the
linker, regardless of any factory passed. Both constructions are
**offline-safe**: `RolloutClient.__init__` only resolves a token
provider (l.786), and `PostgresSearch.__init__` is lazy — no network
until the first `search()`/corpus lookup
(`rag/corpus/postgres/search.py:37-57`). And in our Form-2 bundle
configuration the injected `search_client` is never used (see A1). So
a Pipeline-driven local run *works*, but the local rollout backend
cannot be selected through Pipeline's public surface.

**Options that avoid editing site-packages** (dual-backend design):
1. **Direct construction** — build `SearchAgentLinker(...,
   rollout_client=<LocalRolloutRunner or RolloutClient>)` ourselves,
   as `test_linker.py:63-83` already does. Cleanest; bypasses
   `_build_linker` entirely.
2. **Runtime monkeypatch from repo code** — replace the module-level
   `benchmax.rag.qa_generation.pipeline._build_rollout_client` before
   `Pipeline.run()`. Keeps the full Pipeline flow; patch lives in this
   repo, site-packages untouched on disk.

Either way, backend selection should be a single config flag that picks
which client object gets injected — `RolloutClient` (Castform) or
`LocalRolloutRunner` (local) — so both remain testable side by side.

**Smallest seam:** Replace the `rollout_client` argument with a
`LocalRolloutRunner` that implements `stream_rollout(**kwargs)`.
The linker only calls one method: `self._rollout_client.stream_rollout(**kwargs)` (l.315).

**Required interface for the local runner:**

```python
class LocalRolloutRunner:
    def stream_rollout(
        self,
        raw_example: dict[str, Any],
        env_cls_path: str | None = None,
        env_metadata_path: str | None = None,
        *,
        env_cls_bytes: bytes | None = None,
        env_metadata_bytes: bytes | None = None,
        example_index: int = 0,
        llm_base_url: str | None = None,
        llm_model: str = "gpt-5.4-nano",
        llm_api_key: str = "",
        llm_api_version: str = "",
        max_turns: int = 4,
        max_tool_calls: int = 8,
        max_completion_tokens: int = 4024,
        capture_messages: bool = False,
        full_messages: bool = False,
        include_event_meta: bool = True,
    ) -> dict[str, Any]:
        ...
```

Return value must include at minimum (when `capture_messages=True`):
```python
{
    "event": "rollout_completed",
    "success": True,
    "messages": [...]       # list of {role, content} dicts
}
```

**Auth the local path skips:** The entire bearer-token flow
(`_token_provider`, `_BearerAuth`, the `Authorization` header, the
platform-service proxy that mints act_as JWTs). The local runner calls
the LLM API directly with `llm_api_key`.

**No site-packages edits required.** The injection point is clean.

---

## Part B — What the linker consumes from the result

### B4. Parsing after rollout returns

`_link_with_llm()` at l.201-204 receives the result and extracts:

```python
result = self._run_rollout(raw_example, hop_count=hop_count)
messages = result.get("messages", [])
queries = _extract_queries(messages)
evidence_chain = _extract_evidence_chain(messages)
```

#### Query extraction: `_extract_queries()` (l.484-515)

Iterates all messages. Extracts search queries from two formats:

1. **Structured tool_use blocks** (l.495-503): content is `list[dict]`,
   looks for blocks with `type == "tool_use"`, reads `block["input"]["query"]`.

2. **Text `<tool_call>` XML** (l.504-514): content is `str`, regex
   `_TOOL_CALL_RE` (l.470-472) finds `<tool_call>...</tool_call>` blocks,
   parses JSON inside, reads `payload["arguments"]["query"]` or
   `payload["input"]["query"]`.

Deduplicates queries by value. Returns `list[str]`.

**Requirement:** Messages must contain assistant messages with either
structured `tool_use` blocks or `<tool_call>` XML that includes a
`query` field in the tool arguments.

#### Evidence chain extraction: `_extract_evidence_chain()` (l.518-542)

Searches messages **in reverse** (last message first). For each message,
joins text blocks if content is a list. Applies regex `_EVIDENCE_CHAIN_RE`
(l.473-474) to find `<evidence_chain>...</evidence_chain>` blocks.

From within the evidence chain, extracts:
- `chunk_reasons`: via `_CHUNK_ROLE_RE` (l.476-478) — matches
  `<chunk role="secondary" ...>reason text</chunk>`
- `connection`: via `_CONNECTION_RE` (l.479-481) — matches
  `<connection>explanation</connection>`

Returns:
```python
{
    "raw": str,                # full text inside <evidence_chain>
    "chunk_reasons": [str],    # text inside each <chunk role="secondary"> tag
    "connection": str,         # text inside <connection> tag, or ""
}
```

Or `{}` if no evidence chain found.

**Requirement:** The LLM's final assistant message must contain an
`<evidence_chain>` XML block with `<chunk>` and `<connection>`
sub-elements, matching the system prompt template in `LinkerEnv`
(`linker_env.py` l.63-68).

#### Confidence computation: `_compute_confidence()` (l.421-444)

Weighted average of three signals:
- **fulfillment** (40%): `min(len(secondary_chunks) / n_secondaries, 1.0)`
- **survival** (30%): `len(secondary_chunks) / pre_filter_count`
- **chain_score** (30%):
  - `1.0` if `evidence_chain["connection"]` is non-empty
  - `0.3` if `evidence_chain["raw"]` is non-empty (but no connection)
  - `0.0` otherwise

#### LLM fallback trigger conditions

In `link()` (l.146-178):

1. **Use-LLM gate** (l.166): LLM path is taken when either:
   - `random.random() < search_agent_pct` (configured to 1.0 in our runs)
   - `confidence < 0.5` from the metadata linker pass

2. **Fallback to metadata** (l.173-178): If `_link_with_llm()` raises ANY
   exception and `cfg.fallback_to_metadata` is True (default), falls back
   to the metadata linker result with `llm_fallback = True` in structural_hints.

3. **Empty result** (l.206-207): If `_extract_queries()` returns no queries,
   returns an empty bundle with reason `"no_queries"` (target_hop_count=1,
   confidence 0.0, linker tag `"search_agent"` vs `"search_agent_v2"` on
   success — see `_empty_bundle` l.446-462).

4. **Not-a-chunk guard** (l.191-192): if the primary lacks a `.hash`
   attribute, `_link_with_llm` returns an empty bundle with reason
   `"not_a_chunk"` before any rollout happens.

### B5. Model used today

The linker's LLM model flows through from the generation config:

- `pipeline.py` l.268-276: `llm_model=llm_cfg.model` where `llm_cfg` is
  `cfg.generation.llm_direct`.
- `LLMDirectGenerationConfig.model` default is `"gpt-5.4"` (pipeline_config.py).
- Our run scripts set it to `"gpt-5.4"` explicitly
  (run_natural_multihop.py l.218).
- `test_linker.py` l.80 passes `llm_model="gpt-5.4"`.

The `_VALIDATION_MODEL` in `platform/client.py` l.512 is `"gpt-5.4-nano"` —
the default for `stream_rollout`'s `llm_model` param, but the linker
always overrides it.

**Bottom line: the linker runs `gpt-5.4` via OpenAI API (`https://api.openai.com/v1`).**

---

## Part C — What the remote service does with the env

### C6. Server-side env lifecycle

#### Bundle format

Created by `dump_bundle()` at `bundle.py:73`:
```python
cloudpickle.dumps((env_class, constructor_args))
```

Reversed by `load_bundle()` at `bundle.py:204`:
1. `cloudpickle.loads(pickled)` → `(env_class, constructor_args)`
2. Validates `issubclass(env_class, BaseEnv)`
3. Optionally instantiates: `env_class(**constructor_args)`

Metadata sidecar (`env_metadata.json`) carries `BundleMetadata`
(`bundle.py:36`): `pip_dependencies`, `python_version`,
`benchmax_version`, `env_class_source`.

#### Env method sequence (server-side mirror)

The authoritative reference is `_run_local_checks()` in
`platform/validation.py:169`, whose docstring says *"Mirrors how the
trainer calls env methods"*:

1. **`dataset_preprocess(example)`** — classmethod, turns raw dict into
   `Example` (TypedDict, `envs/types.py:100-124`: `id`,
   `prompt_messages`, `task`, `init_rollout_args`). Note:
   `make_example()` (`envs/example_id.py:105-149`) **prepends the
   system prompt into `prompt_messages`** as a `{"role": "system"}`
   message (l.139-143) — so the preprocessed example already contains
   the system message, without tool defs.
2. **Instantiate** — `env_class(**constructor_args)` from the unpickled tuple
3. **`list_tools()`** → `List[ToolDefinition]` — declares tool schema(s)
4. **Render tool defs into the system message** — per the docstring at
   `example_id.py:121-127`, the trainer renders tools into the first
   system message at LLM-call time. Equivalent formulation:
   `get_system_prompt(add_tool_defs=True)` (`base_env.py:185-192`) =
   `render_tools_prompt(await list_tools(), system_prompt)`
   (`prompts/tools.py:47`).
5. **Conversation loop** — the server drives LLM call loop:
   - Send messages to LLM (system prompt + conversation history)
   - Parse assistant response for `<tool_call>` XML or structured tool_calls
   - Dispatch each call to **`run_tool(rollout_id, tool_name, **tool_args)`**
   - Append tool result to conversation
   - Repeat until LLM produces no tool calls, or budget exhausted
6. **`compute_reward(rollout_id, messages, task)`** → `Dict[str, float]`
7. **`release_rollout(rollout_id)`** / **`shutdown()`**

**All env interface methods are `async`** (`base_env.py:143-205`:
`list_tools`, `run_tool`, `compute_reward`, `get_system_prompt`,
`init_rollout`, `release_rollout`, `shutdown`; `dataset_preprocess` is
the sync exception). The local runner needs an event loop —
`platform/validation.py` drives the same methods via a shared-loop
`_run_async` helper (see `_shutdown_shared_loop` l.44 for the cleanup
pattern it uses to avoid "Event loop is closed" warnings).

#### Tool rendering format

`render_tools_prompt()` (`prompts/tools.py:47`) converts `ToolDefinition`
objects to OpenAI function-call format via `mcp2openai()` (`tools.py:6`),
then wraps them in `<tools>` XML. The expected response format uses:
```
<tool_call>{"name": "...", "arguments": {...}}</tool_call>
```

#### LinkerEnv specifics

`LinkerEnv` (`envs/postgres_search/linker_env.py`):

- **`system_prompt`** (l.107): static class attribute (`_SYSTEM_PROMPT`,
  l.22-69) with multi-hop evidence-chain instructions; the
  `<evidence_chain>` output template is at l.63-68
- **`list_tools()`** (l.155): returns a single `search` tool. Schema
  (l.129-146): `query` (string, required), `limit` (integer, optional,
  default 10)
- **`run_tool()`** (l.158): dispatches to `_search_tool()`; unknown tool
  → `"Error: Unknown tool '...'"` string (l.159-160)
- **`_search_tool(query, limit=10)`** (l.196): calls
  `self._search.search(query=query, mode=self._default_mode, top_k=limit)`,
  formats results (`_format_results` l.212: `"{i}. [source: ...]
  (score: {x:.2f})\n   {content}"`), truncates to 8000 chars
  (`MAX_TOOL_OUTPUT_CHARS` l.19). Search exceptions are caught and
  returned as `"Error:\n{traceback}"` strings (l.209-210) — the rollout
  keeps going.
- **`_default_mode` selection** (l.119-127): `"hybrid"` if in
  `search.available_modes`, else `"lexical"`, else first available.
  `PostgresSearch.available_modes` is `["lexical"]`
  (`rag/corpus/postgres/search.py:95-97`), so today's rollouts search
  in lexical mode. ⚠ A local SearchClient that advertises `"hybrid"`
  would silently change the linker's search behavior — keep
  `available_modes` parity in mind (ties into the BM25-vs-embedding
  open fork).
- **`dataset_preprocess()`** (l.164-181): builds the user prompt from
  `target_n`, `reasoning_mode` (hint text per mode at l.71-87), and
  `example["prompt"]` (primary chunk content); attaches
  `system_prompt=cls.system_prompt` via `make_example`
- **`compute_reward()`** (l.183-190): returns `{"linking": 1.0}` always
- **Constructor** (l.109-118): `search: SearchClient`, keyword-only
  `max_search_calls: int = 3`, `**kwargs`

### C7. Budget enforcement — service-side only

Budget limits are passed as the `options` dict in the rollout request
payload (`client.py:921-923`):

```python
"options": {
    "max_turns": max_turns,
    "max_tool_calls": max_tool_calls,
    "max_completion_tokens": max_completion_tokens,
}
```

The env declares **advisory hints** via class attributes on `BaseEnv`
(`base_env.py:33-34`):
- `recommended_max_turns: Optional[int] = None`
- `recommended_max_tool_calls: Optional[int] = None`

These are NOT enforced by the env.

LinkerEnv takes `max_search_calls` in its constructor but the stored
`self._max_search_calls` (l.117) is **never read anywhere** — not in
`run_tool()`, and not in prompt rendering either (the system prompt is
the static `_SYSTEM_PROMPT`; contrast SearchEnv, whose
`render_system_prompt(..., max_search_calls=N)` bakes the budget into
the prompt text, `search_env.py:139-156`). It is dead config for
LinkerEnv. (An earlier draft of this note said it was "used for system
prompt rendering" — that's true of SearchEnv only.)

For SearchEnv (relevant if env_rollout returns): `run_tool` does not
block over-budget calls either (`search_env.py:255-259`);
`max_search_calls` is enforced only **reward-side** — the
search-efficiency component zeroes out when
`search_within_budget(calls, max)` fails (`search_env.py:469`).

**Implication:** The local runner must enforce `max_turns`,
`max_tool_calls`, and `max_completion_tokens` itself, in exactly one
place (the conversation loop). Neither env blocks tool dispatch.

---

## Part D — Dual-backend coexistence

### D8. Bundle path references (all locations)

#### Writers (1 file, 2 write sites)

| File | Line | Path expression | Bundle type |
|------|------|----------------|-------------|
| `build_env_bundle.py` | 97 | `"env_cls.pkl"` (project root) | SearchEnv |
| `build_env_bundle.py` | 122 | `"linker_env_cls.pkl"` (project root) | LinkerEnv |

Metadata sidecars written at lines 103 and 128, same directory.

#### Readers (7 files, 12 read sites)

| File | Line | Path expression | Bundle type |
|------|------|----------------|-------------|
| `run_natural_multihop.py` | 210 | `PROJECT_DIR / "linker_env_cls.pkl"` | LinkerEnv |
| `run_natural_multihop.py` | 211 | `PROJECT_DIR / "linker_env_metadata.json"` | LinkerEnv meta |
| `run_natural_multihop_batch5.py` | 259 | `PROJECT_DIR / "linker_env_cls.pkl"` | LinkerEnv |
| `run_natural_multihop_batch5.py` | 260 | `PROJECT_DIR / "linker_env_metadata.json"` | LinkerEnv meta |
| `test_linker.py` | 73 | `Path(__file__).parent / "linker_env_cls.pkl"` | LinkerEnv |
| `test_linker.py` | 74 | `Path(__file__).parent / "linker_env_metadata.json"` | LinkerEnv meta |
| `debug_rollout_messages.py` | 21 | `PROJECT_DIR / "linker_env_cls.pkl"` | LinkerEnv |
| `debug_rollout_messages.py` | 22 | `PROJECT_DIR / "linker_env_metadata.json"` | LinkerEnv meta |
| `debug_linking.py` | 136 | `PROJECT_DIR / "linker_env_cls.pkl"` | LinkerEnv |
| `debug_linking.py` | 137 | `PROJECT_DIR / "linker_env_metadata.json"` | LinkerEnv meta |
| `run_pipeline.py` | 94 | `PROJECT_DIR / "env_cls.pkl"` | SearchEnv |
| `run_pipeline.py` | 95 | `PROJECT_DIR / "env_metadata.json"` | SearchEnv meta |
| `dump_corpus_profile.py` | 87 | `PROJECT_DIR / "env_cls.pkl"` | SearchEnv |
| `dump_corpus_profile.py` | 88 | `PROJECT_DIR / "env_metadata.json"` | SearchEnv meta |

#### Proposed per-backend layout

```
chase_eval_benchmax/
  bundles/
    local/
      env_cls.pkl
      env_metadata.json
      linker_env_cls.pkl
      linker_env_metadata.json
    castform/
      env_cls.pkl
      env_metadata.json
      linker_env_cls.pkl
      linker_env_metadata.json
```

Note: `build_env_bundle.py` **already** selects the backend via the
`SEARCH_BACKEND` env var (l.47: `local` → `src.local_search.LocalBM25Search`,
`postgres` → `PostgresSearch`) and stamps `"search_backend"` into both
metadata sidecars (l.102, l.127) — so bundle provenance is already
recorded and inspectable. Only the fixed output paths (l.97, l.122)
cause the clobbering.

Changes required:
1. `build_env_bundle.py` — write to `bundles/{backend}/` instead of
   project root (keyed off the existing `SEARCH_BACKEND` var)
2. All reader files — resolve bundle dir from a config flag or env var
3. `test_linker.py` — uses `Path(__file__).parent` so needs special
   handling (accept the backend selection var)

All changes are mechanical path-prefix swaps.

### D9. Minimal Castform health-check test

The cheapest way to verify the Castform path is alive:

```python
from benchmax.rag.corpus.postgres.search import PostgresSearch
from benchmax import config

search = PostgresSearch(
    corpus_name="chase_help_2026_05_27",
    base_url=config.platform_url(),
)
results = search.search("test query", mode="lexical", top_k=1)
assert len(results) >= 1
assert "content" in results[0]
```

This exercises platform URL resolution, bearer token auth, corpus name
lookup, BM25 search, and result deserialization. Stateless HTTP, no
rollout credits, sub-second.

⚠ **One side-effect caveat:** name-based lookup goes through
`client.get_or_create_corpus(name)` (`rag/corpus/postgres/search.py:59-64`)
— a typo'd corpus name would silently **create** an empty corpus. Pass
`corpus_id=` explicitly (the run config already has it:
`corpus_id="6558ec44-c948-4ed0-a099-63dd786078ad"`,
`run_natural_multihop.py:188`) to skip the lookup and make the health
check strictly read-only.

A single end-to-end linker rollout in Castform mode would cost one
rollout credit and an OpenAI API call (~$0.01-0.03). No teardown needed
(LinkerEnv holds no rollout state; `release_rollout`/`shutdown` are
BaseEnv no-ops).

---

## Summary — what the local runner must do

A `LocalRolloutRunner` must:

1. Accept the same `stream_rollout(**kwargs)` signature as `RolloutClient`
   (at minimum the kwargs the linker passes — see A1).

2. Unpickle the env bundle (or accept a directly-constructed env), call
   `dataset_preprocess(raw_example)` to get the `Example` (its
   `prompt_messages` already include the system message), call
   `list_tools()` for tool defs, render tool definitions into the
   system message (equivalently `get_system_prompt(add_tool_defs=True)`).

3. Drive an LLM conversation loop: send system+user prompt to the LLM
   API, parse tool calls from the response, dispatch them via
   `env.run_tool()`, append tool results, repeat until `max_turns` /
   `max_tool_calls` / no more tool calls. All env interface methods are
   **async** — the runner owns an event loop.

4. **Enforce budgets itself** — the env does not enforce them.

5. Return `{"event": "rollout_completed", "success": True, "messages": [...]}`
   where messages contain `{role, content}` dicts with either structured
   `tool_use` blocks or `<tool_call>` XML with `query` fields, and the
   final assistant message contains `<evidence_chain>` XML.

6. Include **all roles** (user, assistant, tool/tool_result) in the
   messages list — the query extractor scans all of them.

## Site-packages impact

**No site-packages edits required**, with one caveat. The
`SearchAgentLinker` constructor injection is clean — pass any object
implementing `stream_rollout()`. Bundle path changes are all in
project-local files.

The caveat: **`Pipeline` has no injection seam for the linker's rollout
client** — `rollout_client_factory` reaches only the env_rollout
filter, and `_build_linker` hard-codes `RolloutClient` + `PostgresSearch`
(see A3). This does not force editing site-packages, but it does force
a design choice: either construct `SearchAgentLinker` directly in our
run scripts (test_linker.py pattern) or monkeypatch
`pipeline._build_rollout_client` at runtime from repo code. Both keep
the Castform path selectable side by side.

## SearchClient protocol (for the search backend)

Any search backend plugged into LinkerEnv must implement:

| Method / attr      | Signature                                      | Notes                           |
|--------------------|-------------------------------------------------|---------------------------------|
| `search()`         | `(query, mode='auto', top_k=10) → list[dict]`  | Each dict: content, source, metadata, score |
| `embed()`          | `(text) → list[float] \| None`                  | Can return None                 |
| `available_modes`  | `@property → list[str]`                         | e.g. `["lexical"]`             |
| `get_params()`     | `() → dict`                                     | Arbitrary metadata             |

Must be pickle-safe (used in cloudpickle bundle).
