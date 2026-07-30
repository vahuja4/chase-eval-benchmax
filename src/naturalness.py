"""Naturalness judge, rubric v2 (banded conciseness), shared module.

Extracted from run_multihop_batch6.py after the ThinkingBlock crash
(known_issues #7): the batch-5-era parser read ``response.content[0].text``,
which raises AttributeError when the model emits a thinking block before
the text block. ``_response_text`` takes the first block that actually has
text. Conciseness and overall = min(dims) are enforced in code via
``apply_banded_scores``.

Model string is byte-identical to batch5's — never change the judge model
and the rubric in the same run.
"""

from __future__ import annotations

import json
import re

from anthropic import Anthropic

from src.query_length import apply_banded_scores, count_words

JUDGE_MODEL = "claude-sonnet-5"
NATURALNESS_THRESHOLD = 0.6

NATURALNESS_JUDGE_PROMPT = """You are evaluating whether a question sounds natural — like something a real person would type or ask.

Question: {question}

Score this question on a 0.0–1.0 scale across these dimensions, then give an overall score:

1. **Single intent** (0–1): Does this read as ONE coherent thing the person wants to know? Or does it stitch together multiple unrelated sub-questions?
2. **Conciseness** (0–1): Score strictly by word count — this question is {word_count} words long: 15 words or fewer → 1.0; 16–20 words → 0.9; 21–25 words → 0.7; 26–35 words → 0.4; more than 35 words → 0.1.
3. **Natural phrasing** (0–1): Does it sound like something you'd type into a search bar or ask a support agent? Red flags: "If someone used X in two different ways...", role-playing scenarios ("I'm advising a first-time borrower who..."), excessive hedging.
4. **Plausible intent** (0–1): Is there a realistic reason a single person would ask exactly this? Or was it manufactured to connect unrelated topics?

Respond in JSON:
```json
{{"single_intent": 0.0, "conciseness": 0.0, "natural_phrasing": 0.0, "plausible_intent": 0.0, "overall": 0.0, "reasoning": "..."}}
```

The overall score should be the minimum of the four dimension scores (one bad dimension fails the whole question)."""


def _response_text(response) -> str:
    """First text block's content — robust to leading thinking blocks."""
    for block in response.content:
        text = getattr(block, "text", None)
        if text:
            return text
    return "{}"


def judge_naturalness(client: Anthropic, question: str, model: str = JUDGE_MODEL) -> dict:
    """Run the naturalness judge; band conciseness and overall enforced in code."""
    word_count = count_words(question)
    response = client.messages.create(
        model=model,
        max_tokens=1024,
        system="You are a question naturalness evaluator. Be strict. Respond with JSON only.",
        messages=[
            {"role": "user", "content": NATURALNESS_JUDGE_PROMPT.format(
                question=question, word_count=word_count)},
        ],
    )
    raw = _response_text(response)
    try:
        scores = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            scores = json.loads(match.group())
        else:
            scores = {"overall": 0.0, "reasoning": "Failed to parse judge response"}
    return apply_banded_scores(scores, word_count)
