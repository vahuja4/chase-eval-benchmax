"""Offline tests for OpenAI tool_calls query extraction (src/rollout_compat.py)."""

import json

import benchmax.rag.qa_generation.search_agent_linker as linker_mod

from src.rollout_compat import (
    extract_openai_tool_call_queries,
    install_openai_toolcall_extraction,
)

OPENAI_MSG = {
    "role": "assistant",
    "content": "",
    "tool_calls": [
        {
            "id": "call_1",
            "type": "function",
            "function": {
                "name": "search",
                "arguments": json.dumps({"query": "chase points transfer partners", "limit": 5}),
            },
        }
    ],
}

XML_MSG = {
    "role": "assistant",
    "content": '<tool_call>\n{"name": "search", "arguments": {"query": "grace period cash advance"}}\n</tool_call>',
}

ANTHROPIC_MSG = {
    "role": "assistant",
    "content": [
        {"type": "text", "text": "searching"},
        {"type": "tool_use", "name": "search", "id": "t1",
         "input": {"query": "secured card deposit", "limit": 10}},
    ],
}


def test_extracts_openai_string_arguments():
    assert extract_openai_tool_call_queries([OPENAI_MSG]) == [
        "chase points transfer partners"
    ]


def test_extracts_openai_dict_arguments():
    msg = {"role": "assistant", "content": "", "tool_calls": [
        {"function": {"name": "search", "arguments": {"query": "dict args"}}}
    ]}
    assert extract_openai_tool_call_queries([msg]) == ["dict args"]


def test_ignores_malformed_tool_calls():
    msgs = [
        {"role": "assistant", "tool_calls": [
            {"function": {"arguments": "not json"}},
            "not a dict",
            {"function": {"arguments": json.dumps({"limit": 5})}},  # no query
        ]},
        {"role": "user", "content": "plain"},
    ]
    assert extract_openai_tool_call_queries(msgs) == []


def test_patched_extractor_handles_all_three_formats():
    uninstall = install_openai_toolcall_extraction()
    try:
        queries = linker_mod._extract_queries([ANTHROPIC_MSG, XML_MSG, OPENAI_MSG])
        assert "secured card deposit" in queries
        assert "grace period cash advance" in queries
        assert "chase points transfer partners" in queries
    finally:
        uninstall()


def test_patched_extractor_dedups_across_formats():
    uninstall = install_openai_toolcall_extraction()
    try:
        dup_openai = {"role": "assistant", "content": "", "tool_calls": [
            {"function": {"name": "search",
                          "arguments": json.dumps({"query": "grace period cash advance"})}}
        ]}
        queries = linker_mod._extract_queries([XML_MSG, dup_openai])
        assert queries == ["grace period cash advance"]
    finally:
        uninstall()


def test_install_is_idempotent_and_uninstall_restores():
    original = linker_mod._extract_queries
    first = install_openai_toolcall_extraction()
    patched = linker_mod._extract_queries
    assert patched is not original
    second = install_openai_toolcall_extraction()
    assert linker_mod._extract_queries is patched
    second()
    assert linker_mod._extract_queries is patched
    first()
    assert linker_mod._extract_queries is original
