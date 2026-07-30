"""Castform liveness check (notes/rollout_interface.md D9).

Cheapest call proving corpus + auth + API are alive: one lexical BM25
query through PostgresSearch. Passing corpus_id explicitly keeps it
strictly read-only — name-based lookup goes through get_or_create_corpus,
which would create an empty corpus on a typo'd name.

Deselected by default (see pytest.ini). Run with:
    pytest -m castform
"""

import os

import pytest
from dotenv import load_dotenv

load_dotenv()

pytestmark = [
    pytest.mark.castform,
    pytest.mark.skipif(
        not os.environ.get("PLATFORM_API_KEY"),
        reason="PLATFORM_API_KEY not set",
    ),
]

CORPUS_NAME = "chase_help_2026_05_27"
CORPUS_ID = "6558ec44-c948-4ed0-a099-63dd786078ad"


def test_castform_corpus_search_alive():
    from benchmax import config
    from benchmax.rag.corpus.postgres.search import PostgresSearch

    # No token_provider: the default credential seam (platform_bearer)
    # resolves PLATFORM_API_KEY from the environment without capturing a
    # literal key in a closure.
    search = PostgresSearch(
        corpus_name=CORPUS_NAME,
        base_url=config.platform_url(),
        corpus_id=CORPUS_ID,
    )
    results = search.search("credit card annual fee", mode="lexical", top_k=1)
    assert results, "Castform BM25 search returned no results"

    # SearchClient result contract (notes/rollout_interface.md).
    result = results[0]
    for key in ("content", "source", "metadata", "score"):
        assert key in result, f"search result missing contract key {key!r}"
    assert result["content"], "search result has empty content"
    assert isinstance(result["metadata"], dict)
    assert isinstance(result["score"], (int, float))
