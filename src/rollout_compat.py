"""OpenAI tool_calls compatibility for the search-agent linker.

Castform rollout workers return OpenAI-format assistant messages: empty
``content`` plus a ``tool_calls`` list whose ``function.arguments`` is a
JSON string. The installed benchmax ``_extract_queries`` only parses
Anthropic ``tool_use`` content blocks and Hermes ``<tool_call>`` XML, so
every rollout yields no queries → empty anchor bundle (``no_queries``) →
single-chunk items that can never pass as multi-hop. Same format-mismatch
family as known_issues.md #1 (``_count_tool_calls``).

Repo-local monkeypatch (site-packages untouched): ``_link_with_llm`` looks
up ``_extract_queries`` as a module global at call time, so replacing the
module attribute is sufficient.
"""

from __future__ import annotations

import json
from typing import Any

import benchmax.rag.qa_generation.search_agent_linker as _linker_mod


def extract_openai_tool_call_queries(messages: list[dict[str, Any]]) -> list[str]:
    """Pull search queries out of OpenAI-format ``tool_calls`` lists."""
    queries: list[str] = []
    for msg in messages:
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            func = tc.get("function", {})
            raw_args = func.get("arguments", "{}") if isinstance(func, dict) else "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
            except (json.JSONDecodeError, ValueError):
                continue
            query = args.get("query") if isinstance(args, dict) else None
            if query and query not in queries:
                queries.append(query)
    return queries


def install_openai_toolcall_extraction():
    """Extend linker query extraction with OpenAI tool_calls (idempotent).

    Wraps the module-global ``_extract_queries``; returns an uninstall
    callable that restores the original.
    """
    original = _linker_mod._extract_queries
    if getattr(original, "_openai_toolcall_compat", False):
        return lambda: None

    def _patched(messages: list[dict[str, Any]]) -> list[str]:
        queries = original(messages)
        for query in extract_openai_tool_call_queries(messages):
            if query not in queries:
                queries.append(query)
        return queries

    _patched._openai_toolcall_compat = True
    _linker_mod._extract_queries = _patched

    def _uninstall():
        _linker_mod._extract_queries = original

    return _uninstall
