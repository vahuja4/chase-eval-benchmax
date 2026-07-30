"""Offline tests for the query-length constraint (src/query_length.py)
and dedup collision attribution (src/dedup_attribution.py)."""

import json

import pytest

import benchmax.rag.qa_generation.pipeline as pipeline_mod
from benchmax.rag.qa_generation.generated_qa import FilterVerdict, GeneratedQA
from benchmax.rag.qa_generation.pipeline_config import (
    FilteringConfig,
    PipelineConfig,
    PlatformConfig,
)
from benchmax.rag.qa_generation.transformers.dedup import IncrementalDeduplicator

from src.dedup_attribution import seed_and_instrument
from src.query_length import (
    HARD_CAP,
    REFINEMENT_FEEDBACK,
    STAGE_NAME,
    QueryLengthCapFilter,
    apply_banded_scores,
    conciseness_band,
    count_words,
    install_query_length_filter,
)


def _cfg(**kwargs) -> PipelineConfig:
    return PipelineConfig(platform=PlatformConfig(), **kwargs)


def _question(n_words: int) -> str:
    return " ".join(f"w{i}" for i in range(n_words - 1)) + " end?"


def _item(question: str) -> GeneratedQA:
    return GeneratedQA(qa={"question": question, "answer": "an answer",
                           "reference_chunks": [], "qa_type": "multi_hop"})


# ---------------------------------------------------------------------------
# count_words / conciseness_band / apply_banded_scores
# ---------------------------------------------------------------------------

def test_count_words_whitespace_split():
    assert count_words("how do points transfer?") == 4
    assert count_words("  spaced   out  words ") == 3
    assert count_words("") == 0
    assert count_words(_question(24)) == 24


@pytest.mark.parametrize("n,expected", [
    (1, 1.0), (15, 1.0),
    (16, 0.9), (20, 0.9),
    (21, 0.7), (25, 0.7),
    (26, 0.4), (35, 0.4),
    (36, 0.1), (60, 0.1),
])
def test_conciseness_band_boundaries(n, expected):
    assert conciseness_band(n) == expected


def test_apply_banded_scores_overrides_conciseness_and_overall():
    model_scores = {"single_intent": 0.8, "conciseness": 1.0,
                    "natural_phrasing": 0.9, "plausible_intent": 0.7,
                    "overall": 0.95, "reasoning": "fine"}
    out = apply_banded_scores(model_scores, word_count=30)
    assert out["conciseness"] == 0.4  # banded, not the model's 1.0
    assert out["overall"] == 0.4  # min of dimensions, not the model's 0.95
    assert out["reasoning"] == "fine"
    assert model_scores["conciseness"] == 1.0  # input not mutated


def test_apply_banded_scores_over_25_words_fails_cutoff():
    perfect = {"single_intent": 1.0, "conciseness": 1.0,
               "natural_phrasing": 1.0, "plausible_intent": 1.0, "overall": 1.0}
    assert apply_banded_scores(perfect, word_count=26)["overall"] < 0.6


def test_apply_banded_scores_missing_dimension_falls_back_to_model_overall():
    out = apply_banded_scores({"overall": 0.0, "reasoning": "Failed to parse"},
                              word_count=10)
    assert out["overall"] == 0.0  # parse failure still fails closed


# ---------------------------------------------------------------------------
# QueryLengthCapFilter
# ---------------------------------------------------------------------------

def test_filter_passes_24_words_untouched():
    item = _item(_question(24))
    QueryLengthCapFilter().evaluate([item], {})
    assert item.filter_verdict is None  # None, not "passed" — see quality_gate skip


def test_filter_flags_26_words_for_refinement():
    item = _item(_question(26))
    context = {}
    QueryLengthCapFilter().evaluate([item], context)
    verdict = item.filter_verdict
    assert verdict is not None
    assert verdict.status == "needs_refinement"
    assert verdict.reason == "query_too_long"
    assert verdict.metadata["refinement_hint"] == REFINEMENT_FEEDBACK
    assert verdict.metadata["word_count"] == 26
    assert str(HARD_CAP) in verdict.reasoning
    assert context[f"{STAGE_NAME}_stats"] == {"evaluated": 1, "flagged": 1}


def test_filter_boundary_25_words_passes():
    item = _item(_question(25))
    QueryLengthCapFilter().evaluate([item], {})
    assert item.filter_verdict is None


def test_filter_skips_items_already_failed():
    item = _item(_question(40))
    prior = FilterVerdict(status="rejected", reason="other", reasoning="x")
    item.filter_verdict = prior
    QueryLengthCapFilter().evaluate([item], {})
    assert item.filter_verdict is prior  # untouched


# ---------------------------------------------------------------------------
# Registration + ordering (repo-side factory patch, no site-packages edits)
# ---------------------------------------------------------------------------

@pytest.fixture
def installed():
    uninstall = install_query_length_filter()
    yield
    uninstall()


def test_factory_patch_registers_stage(installed):
    cfg = _cfg()
    built = pipeline_mod._build_filter_from_stage_name(STAGE_NAME, cfg, source=None)
    assert isinstance(built, QueryLengthCapFilter)


def test_factory_patch_preserves_builtins_and_errors(installed):
    cfg = _cfg()
    builtin = pipeline_mod._build_filter_from_stage_name("quality_gate", cfg, source=None)
    assert type(builtin).__name__ == "QualityGateFilter"
    with pytest.raises(ValueError, match="Unknown filter stage"):
        pipeline_mod._build_filter_from_stage_name("no_such_stage", cfg, source=None)


def test_install_is_idempotent_and_uninstall_restores():
    original = pipeline_mod._build_filter_from_stage_name
    first_uninstall = install_query_length_filter()
    patched = pipeline_mod._build_filter_from_stage_name
    assert patched is not original
    second_uninstall = install_query_length_filter()
    assert pipeline_mod._build_filter_from_stage_name is patched  # no double-wrap
    second_uninstall()
    assert pipeline_mod._build_filter_from_stage_name is patched
    first_uninstall()
    assert pipeline_mod._build_filter_from_stage_name is original


def test_chain_orders_length_cap_before_llm_filters(installed):
    cfg = _cfg(filtering=FilteringConfig(filters=[STAGE_NAME, "quality_gate"]))
    names, chain = pipeline_mod._build_filter_chain(cfg, source=None)
    assert names == [STAGE_NAME, "quality_gate"]
    assert isinstance(chain[0], QueryLengthCapFilter)


# ---------------------------------------------------------------------------
# Dedup seeding with collision attribution
# ---------------------------------------------------------------------------

def test_dedup_collision_attributes_originating_seed_file(tmp_path):
    log = tmp_path / "collisions.jsonl"
    dedup = IncrementalDeduplicator()
    prior = [
        ("fileA.jsonl", "how do chase ultimate rewards points transfer to airline partners"),
        ("fileB.jsonl", "what happens to my escrow account when I refinance a mortgage"),
    ]
    seed_and_instrument(dedup, prior, log)

    duplicate = _item(prior[0][1])  # exact copy of the fileA question
    fresh = _item("does a cash advance still get a grace period?")
    unique, duplicates = dedup.check_batch([duplicate, fresh])

    assert [d.qa["question"] for d in duplicates] == [prior[0][1]]
    assert unique == [fresh]
    assert duplicate.filter_verdict.reason == "early_near_duplicate"
    assert duplicate.filter_verdict.metadata["matched_source_file"] == "fileA.jsonl"

    records = [json.loads(line) for line in log.read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["matched_source_file"] == "fileA.jsonl"
    assert records[0]["matched_prior_question"] == prior[0][1]
    assert records[0]["similarity"] >= 0.70


def test_dedup_current_run_registrations_are_attributed(tmp_path):
    log = tmp_path / "collisions.jsonl"
    dedup = IncrementalDeduplicator()
    seed_and_instrument(dedup, [("fileA.jsonl", "totally unrelated seed question here")], log)

    accepted = _item("can I set up autopay for my chase credit card online")
    dedup.register_accepted([accepted])
    duplicate = _item("can I set up autopay for my chase credit card online")
    _, duplicates = dedup.check_batch([duplicate])

    assert len(duplicates) == 1
    assert duplicate.filter_verdict.metadata["matched_source_file"] == "current_run"
