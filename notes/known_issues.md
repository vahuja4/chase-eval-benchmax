# Known Issues

## 1. `_count_tool_calls` patch (site-packages)

`_count_tool_calls` in the env rollout filter only counted Anthropic-format tool calls (`tool_use` content blocks). The rollout service returns OpenAI-format messages, so tool calls were never counted — causing the "too few tool calls" check to misfire.

**Patched at:**
```
/Users/vishal/miniconda3/lib/python3.12/site-packages/benchmax/rag/qa_generation/filters/env_rollout.py
```

**What changed:** added `msg.get("tool_calls")` handling in `_count_tool_calls` (line 46) so it recognises both Anthropic and OpenAI message formats.

**Risk:** this patch lives in site-packages and will be lost on reinstall or upgrade. Should be reported upstream.

## 2. Malformed-JSON early stopping on regeneration

The generation LLM occasionally returns malformed JSON during regeneration rounds. After 5 consecutive parse failures the pipeline treats the batch as exhausted and stops early (typically around batch 7–8 in a 30-sample run).

This tends to happen after the pipeline has already used the easier seed chunks and is regenerating from harder ones — the LLM struggles more with the remaining material and produces structurally invalid output more often.
