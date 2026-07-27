"""Tests for LocalBM25Search — contract, known-answer, and replay parity."""

import json
from pathlib import Path

import pytest

from src.local_search import LocalBM25Search

CHUNKS_PATH = "data/snapshots/chase_2026_05_27/chunks.jsonl"


@pytest.fixture(scope="module")
def search():
    return LocalBM25Search(CHUNKS_PATH)


# =========================================================================
# 3a. Contract tests
# =========================================================================

class TestContract:
    REQUIRED_KEYS = {"content", "source", "metadata", "score"}

    def test_result_keys(self, search):
        results = search.search("credit card rewards")
        assert len(results) > 0
        for r in results:
            assert set(r.keys()) == self.REQUIRED_KEYS

    def test_source_equals_metadata_file(self, search):
        results = search.search("checking account fees")
        for r in results:
            assert r["source"] == r["metadata"]["file"]

    def test_raises_on_semantic_mode(self, search):
        with pytest.raises(ValueError, match="Unsupported search mode"):
            search.search("test query", mode="semantic")

    def test_raises_on_hybrid_mode(self, search):
        with pytest.raises(ValueError, match="Unsupported search mode"):
            search.search("test query", mode="hybrid")

    def test_auto_mode_succeeds(self, search):
        results = search.search("savings account", mode="auto")
        assert isinstance(results, list)

    def test_lexical_mode_succeeds(self, search):
        results = search.search("savings account", mode="lexical")
        assert isinstance(results, list)

    def test_available_modes(self, search):
        assert search.available_modes == ["lexical"]

    def test_descending_score_order(self, search):
        results = search.search("mortgage refinance rates")
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_embed_returns_none(self, search):
        assert search.embed("anything") is None

    def test_get_params_keys(self, search):
        params = search.get_params()
        assert "k1" in params
        assert "b" in params
        assert "stemmer" in params
        assert "chunks_path" in params
        assert "num_chunks" in params
        assert params["num_chunks"] > 0

    def test_metadata_keys(self, search):
        results = search.search("auto loan")
        assert len(results) > 0
        expected_meta_keys = {"file", "chunk_id", "page_title", "heading_path", "stratum", "sub_stratum"}
        for r in results:
            assert set(r["metadata"].keys()) == expected_meta_keys

    def test_no_crash_on_gibberish(self, search):
        results = search.search("xyzzy plugh qwerty asdf")
        assert isinstance(results, list)


# =========================================================================
# 3b. Known-answer tests
# =========================================================================

KNOWN_ANSWER_QUERIES = [
    ("Chase Sapphire Reserve annual fee travel credit", "p_00209"),
    ("jumbo loan qualification requirements limits", "p_00296"),
    ("Chase Ultimate Rewards how the program works", "p_00121"),
    ("Freedom Rise credit limit increase after six months", "p_00116"),
    ("what is a joint high yield savings account", "p_00054"),
]


class TestKnownAnswer:
    @pytest.mark.parametrize("query,expected_pid", KNOWN_ANSWER_QUERIES)
    def test_expected_doc_in_top5(self, search, query, expected_pid):
        results = search.search(query, top_k=5)
        found_pids = {r["source"] for r in results}
        assert expected_pid in found_pids, (
            f"Expected {expected_pid} in top-5 for query '{query}', "
            f"got: {[r['source'] for r in results]}"
        )


# =========================================================================
# 3c. Pickle round-trip
# =========================================================================

class TestPickle:
    def test_pickle_roundtrip(self, search):
        import pickle
        state = search.__getstate__()
        assert set(state.keys()) == {"chunks_path", "k1", "b"}

        restored = LocalBM25Search.__new__(LocalBM25Search)
        restored.__setstate__(state)
        results = restored.search("credit card rewards", top_k=3)
        assert len(results) > 0
        assert results[0]["source"] == results[0]["metadata"]["file"]

    def test_pickle_bytes_roundtrip(self, search):
        import pickle
        data = pickle.dumps(search)
        restored = pickle.loads(data)
        results = restored.search("savings account", top_k=3)
        assert len(results) > 0


# =========================================================================
# 3d. Replay parity (always passes; writes report)
# =========================================================================

LINKING_DETAILS_FILES = [
    "outputs/natural_multihop/step_2_linking_details.json",
    "outputs/natural_multihop_batch4/step_2_linking_details.json",
    "outputs/retrieval_filtered_batch3/step_2_linking_details.json",
]


def test_replay_parity(search):
    """Replay all linker queries and measure doc-id overlap.

    Always passes — writes report to notes/local_search_parity.md.
    """
    records = []
    for fpath in LINKING_DETAILS_FILES:
        p = Path(fpath)
        if not p.exists():
            continue
        data = json.loads(p.read_text())
        for entry in data:
            hints = entry.get("linking_hints", {})
            queries = hints.get("queries_used", [])
            if not queries:
                continue
            anchor = entry.get("anchor_bundle", {})
            secondary = anchor.get("secondary_chunks", [])
            original_pids = set()
            for sc in secondary:
                meta = sc.get("metadata", [])
                if isinstance(meta, list):
                    for k, v in meta:
                        if k == "file":
                            original_pids.add(v)
                elif isinstance(meta, dict):
                    if "file" in meta:
                        original_pids.add(meta["file"])
            if not original_pids:
                continue
            records.append({
                "source_file": fpath,
                "task_id": entry.get("task_id", ""),
                "queries": queries,
                "original_pids": original_pids,
            })

    if not records:
        Path("notes").mkdir(exist_ok=True)
        Path("notes/local_search_parity.md").write_text(
            "# Local search replay parity\n\nNo queries with secondary chunks found.\n"
        )
        return

    total_queries = 0
    total_hits = 0
    total_secondary_docs = 0
    ranks_when_found = []
    per_record = []

    for rec in records:
        local_pids_all = set()
        local_ranked = []
        for q in rec["queries"]:
            total_queries += 1
            results = search.search(q, top_k=10)
            result_pids = [r["source"] for r in results]
            local_pids_all.update(result_pids)
            local_ranked.append(result_pids)

        hits = rec["original_pids"] & local_pids_all
        total_secondary_docs += len(rec["original_pids"])
        total_hits += len(hits)

        for pid in hits:
            for result_pids in local_ranked:
                if pid in result_pids:
                    ranks_when_found.append(result_pids.index(pid) + 1)
                    break

        per_record.append({
            "task_id": rec["task_id"],
            "source": rec["source_file"],
            "n_queries": len(rec["queries"]),
            "original_pids": sorted(rec["original_pids"]),
            "hit_pids": sorted(hits),
            "miss_pids": sorted(rec["original_pids"] - hits),
        })

    hit_rate = total_hits / total_secondary_docs if total_secondary_docs else 0
    avg_rank = sum(ranks_when_found) / len(ranks_when_found) if ranks_when_found else float("nan")

    lines = [
        "# Local BM25 search replay parity",
        "",
        "## Methodology",
        "",
        "Replayed all `queries_used` from `step_2_linking_details.json` files",
        "against the local BM25 index (text-only, Snowball English stemmer,",
        "k1=1.5, b=0.75). Compared returned doc ids (top-10) against the",
        "secondary chunks selected in the original Castform runs.",
        "",
        "**Important caveat**: the baseline secondary selections are",
        "post-filtered (400-char minimum, same-file exclusion, dedup,",
        "Jaccard coherence >= 0.15, diversity cap). Hit-rate therefore",
        "understates raw retrieval parity — a miss may mean the local index",
        "retrieved the doc but the linker's downstream filters excluded it,",
        "or the original run's filters selected a different chunk from the",
        "same query results.",
        "",
        "Text-only indexing is a provisional choice. If parity is weak,",
        "text + page_title + heading_path indexing should be compared.",
        "",
        "## Summary",
        "",
        f"- **Total linking records with queries**: {len(records)}",
        f"- **Total queries replayed**: {total_queries}",
        f"- **Unique secondary doc ids (baseline)**: {total_secondary_docs}",
        f"- **Hits (doc id in local top-10)**: {total_hits}",
        f"- **Hit rate**: {hit_rate:.1%}",
        f"- **Average rank when found**: {avg_rank:.1f}",
        "",
        "## Per-record detail",
        "",
        "| Task ID | Source | Queries | Original docs | Hits | Misses |",
        "|---------|--------|---------|---------------|------|--------|",
    ]
    for pr in per_record:
        lines.append(
            f"| {pr['task_id']} | {Path(pr['source']).parent.name} | "
            f"{pr['n_queries']} | {', '.join(pr['original_pids'])} | "
            f"{', '.join(pr['hit_pids']) or '—'} | "
            f"{', '.join(pr['miss_pids']) or '—'} |"
        )

    Path("notes").mkdir(exist_ok=True)
    Path("notes/local_search_parity.md").write_text("\n".join(lines) + "\n")
