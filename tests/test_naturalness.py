"""Offline tests for the shared naturalness judge (src/naturalness.py)."""

import json

from src.naturalness import _response_text


class _ThinkingBlock:
    """Stand-in for anthropic's ThinkingBlock: no .text attribute."""


class _TextBlock:
    def __init__(self, text):
        self.text = text


class _Response:
    def __init__(self, blocks):
        self.content = blocks


def test_response_text_skips_leading_thinking_block():
    payload = json.dumps({"single_intent": 1.0, "overall": 1.0})
    resp = _Response([_ThinkingBlock(), _TextBlock(payload)])
    assert _response_text(resp) == payload


def test_response_text_plain_text_block():
    resp = _Response([_TextBlock("hello")])
    assert _response_text(resp) == "hello"


def test_response_text_no_text_blocks_fails_closed():
    assert _response_text(_Response([_ThinkingBlock()])) == "{}"
    assert _response_text(_Response([])) == "{}"
    assert _response_text(_Response([_TextBlock("")])) == "{}"
