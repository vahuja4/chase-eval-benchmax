"""Seed an IncrementalDeduplicator with prior questions, with attribution.

Batch5 pre-seeded the dedup index but logged nothing, so a collision
against a judge-rejected prior question was invisible. This helper keeps
a metadata list aligned with the deduplicator's ``_accepted_ngrams`` —
``(source_file, question)`` for the seeded prefix, ``("current_run", q)``
for questions accepted during the run — and replaces ``check_batch`` on
the instance with a version that attributes each rejection to the
best-Jaccard match and appends it to a JSONL collision log.

The replacement mirrors upstream ``IncrementalDeduplicator.check_batch``
(benchmax transformers/dedup.py:145-172); benchmax is pinned and treated
as read-only, so drift is handled at upgrade time.
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmax.rag.qa_generation.generated_qa import FilterVerdict, GeneratedQA
from benchmax.rag.qa_generation.transformers.dedup import _jaccard


def seed_and_instrument(
    dedup,
    prior_entries: list[tuple[str, str]],
    collision_log_path: str | Path,
) -> list[tuple[str, str]]:
    """Seed *dedup* with (source_file, question) pairs and attach attribution.

    Returns the live seed-metadata list (index-aligned with
    ``dedup._accepted_ngrams``; grows as the run accepts questions).
    """
    collision_log_path = Path(collision_log_path)
    seed_meta: list[tuple[str, str]] = []

    with dedup._lock:
        for source, question in prior_entries:
            dedup._accepted_ngrams.append(dedup._compute_ngrams(question))
            seed_meta.append((source, question))

    original_register = dedup.register_accepted

    def register_accepted(items: list[GeneratedQA]) -> None:
        for item in items:
            seed_meta.append(("current_run", str(item.qa.get("question", ""))))
        original_register(items)

    def check_batch(items: list[GeneratedQA]):
        with dedup._lock:
            unique: list[GeneratedQA] = []
            duplicates: list[GeneratedQA] = []
            for item in items:
                question = str(item.qa.get("question", ""))
                ngrams = dedup._compute_ngrams(question)
                best_sim, best_idx = 0.0, None
                if ngrams:
                    for idx, accepted in enumerate(dedup._accepted_ngrams):
                        if not accepted:
                            continue
                        sim = _jaccard(ngrams, accepted)
                        if sim > best_sim:
                            best_sim, best_idx = sim, idx
                if best_idx is not None and best_sim >= dedup.similarity_threshold:
                    source, prior_q = (
                        seed_meta[best_idx]
                        if best_idx < len(seed_meta)
                        else ("unknown", "")
                    )
                    record = {
                        "question": question,
                        "matched_source_file": source,
                        "matched_prior_question": prior_q,
                        "similarity": round(best_sim, 4),
                    }
                    collision_log_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(collision_log_path, "a") as f:
                        f.write(json.dumps(record) + "\n")
                    print(
                        f"  [dedup] rejected (sim={best_sim:.2f}, "
                        f"source={source}): {question[:80]}"
                    )
                    item.filter_verdict = FilterVerdict(
                        status="rejected",
                        reason="early_near_duplicate",
                        reasoning="Near-duplicate of already-accepted question.",
                        metadata={
                            "reason_code": "early_near_duplicate",
                            "matched_source_file": source,
                            "similarity": best_sim,
                        },
                    )
                    duplicates.append(item)
                else:
                    unique.append(item)
            return unique, duplicates

    dedup.register_accepted = register_accepted
    dedup.check_batch = check_batch
    return seed_meta
