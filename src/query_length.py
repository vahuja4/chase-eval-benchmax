"""Deterministic query-length constraint for the QA generation pipeline.

Two repo-owned enforcement layers (no site-packages edits):

1. ``QueryLengthCapFilter`` — a deterministic filter registered into
   benchmax's filter chain by name. ``FilteringConfig.filters`` accepts
   arbitrary stage names (config loading never validates them,
   pipeline_config.py:929-942), and the name->filter factory
   ``pipeline._build_filter_from_stage_name`` is a module global resolved
   at call time (pipeline.py:379) — the same monkeypatch seam
   run_natural_multihop_batch5.py already uses for ``auto_tune``.
   Questions over HARD_CAP words get ``needs_refinement`` so the
   regeneration loop shortens them instead of dropping them.

2. ``conciseness_band`` / ``apply_banded_scores`` — the word-banded
   conciseness rubric for the naturalness judge, enforced in code so the
   band (a pure function of word count) and ``overall = min(dimensions)``
   don't depend on the judge model honoring prompt instructions.
"""

from __future__ import annotations

from typing import Any

from benchmax.rag.qa_generation.generated_qa import FilterVerdict, GeneratedQA

STAGE_NAME = "query_length_cap"
HARD_CAP = 25  # deterministic backstop; the prompt targets PROMPT_TARGET
PROMPT_TARGET = 20
REFINEMENT_FEEDBACK = (
    "rewrite as one sentence of 20 words or fewer; keep the multi-hop requirement"
)

# (inclusive upper word bound, conciseness score); scanned in order.
CONCISENESS_BANDS = ((15, 1.0), (20, 0.9), (25, 0.7), (35, 0.4))
CONCISENESS_FLOOR = 0.1

JUDGE_DIMENSIONS = ("single_intent", "conciseness", "natural_phrasing", "plausible_intent")
JUDGE_RUBRIC_VERSION = "naturalness_v2_banded_conciseness"


def count_words(text: str) -> int:
    """Whitespace-token word count (same convention as quality_gate)."""
    return len(text.split())


def conciseness_band(word_count: int) -> float:
    for upper, score in CONCISENESS_BANDS:
        if word_count <= upper:
            return score
    return CONCISENESS_FLOOR


def apply_banded_scores(scores: dict, word_count: int) -> dict:
    """Enforce the banded rubric on a judge response, returning a new dict.

    Conciseness is overridden with the band value; overall is recomputed
    as min of the four dimensions. If any other dimension is missing or
    non-numeric (e.g. a parse-failure response), the model's own overall
    is kept — which fails closed to 0.0 in the parse-failure case.
    """
    out = dict(scores)
    out["conciseness"] = conciseness_band(word_count)
    try:
        out["overall"] = min(float(out[d]) for d in JUDGE_DIMENSIONS)
    except (KeyError, TypeError, ValueError):
        out["overall"] = float(out.get("overall", 0.0) or 0.0)
    return out


class QueryLengthCapFilter:
    """Flags questions over HARD_CAP words for regeneration.

    Runs first in the configurable chain, before any LLM filter. Leaves
    ``filter_verdict`` untouched on passing items — quality_gate skips any
    item with a non-None verdict (quality_gate.py:162), so setting a
    "passed" verdict here would disable it.
    """

    def evaluate(self, items: list[GeneratedQA], context: Any) -> list[GeneratedQA]:
        stats = context.setdefault(
            f"{STAGE_NAME}_stats", {"evaluated": 0, "flagged": 0}
        )
        for item in items:
            if item.filter_verdict is not None and not item.is_passed:
                continue
            question = str(item.qa.get("question", "")).strip()
            n = count_words(question)
            stats["evaluated"] += 1
            if n <= HARD_CAP:
                continue
            stats["flagged"] += 1
            item.filter_verdict = FilterVerdict(
                status="needs_refinement",
                reason="query_too_long",
                reasoning=f"Question is {n} words; hard cap is {HARD_CAP}.",
                metadata={
                    "filter_mode": STAGE_NAME,
                    "reason_code": "query_too_long",
                    "feedback_type": "needs_refinement",
                    "refinement_hint": REFINEMENT_FEEDBACK,
                    "word_count": n,
                },
            )
        return items


def install_query_length_filter():
    """Register STAGE_NAME with benchmax's filter factory (idempotent).

    Wraps the module-global ``pipeline._build_filter_from_stage_name``;
    returns an uninstall callable that restores the previous factory.
    """
    import benchmax.rag.qa_generation.pipeline as pipeline_mod

    original = pipeline_mod._build_filter_from_stage_name
    if getattr(original, "_query_length_cap_installed", False):
        return lambda: None

    def _patched(stage_name, cfg, **kwargs):
        if str(stage_name or "").strip().lower() == STAGE_NAME:
            return QueryLengthCapFilter()
        return original(stage_name, cfg, **kwargs)

    _patched._query_length_cap_installed = True
    pipeline_mod._build_filter_from_stage_name = _patched

    def _uninstall():
        pipeline_mod._build_filter_from_stage_name = original

    return _uninstall
