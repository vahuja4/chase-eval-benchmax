"""Local BM25 search backend replacing Castform's PostgresSearch."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import bm25s
import Stemmer


_METADATA_KEYS = ("file", "chunk_id", "page_title", "heading_path", "stratum", "sub_stratum")


class LocalBM25Search:
    """BM25 search over a local chunks.jsonl file.

    Implements the SearchClient protocol (search, embed, available_modes,
    get_params) as a drop-in replacement for PostgresSearch.
    """

    def __init__(self, chunks_path: str | Path, *, k1: float = 1.5, b: float = 0.75) -> None:
        self._chunks_path = str(chunks_path)
        self._k1 = k1
        self._b = b
        self._chunks: list[dict[str, Any]] | None = None
        self._retriever: bm25s.BM25 | None = None
        self._stemmer: Stemmer.Stemmer | None = None
        self._build_index()

    def _build_index(self) -> None:
        self._stemmer = Stemmer.Stemmer("english")
        chunks: list[dict[str, Any]] = []
        with open(self._chunks_path) as f:
            for line in f:
                line = line.strip()
                if line:
                    chunks.append(json.loads(line))
        self._chunks = chunks
        texts = [c["text"] for c in chunks]
        corpus_tokens = bm25s.tokenize(texts, stemmer=self._stemmer)
        self._retriever = bm25s.BM25(k1=self._k1, b=self._b)
        self._retriever.index(corpus_tokens)

    def _ensure_index(self) -> None:
        if self._retriever is None:
            self._build_index()

    def search(self, query: str, mode: str = "auto", top_k: int = 10) -> list[dict[str, Any]]:
        if mode not in ("auto", "lexical"):
            raise ValueError(
                f"Unsupported search mode: {mode!r}. "
                f"Available modes: {self.available_modes}"
            )
        self._ensure_index()
        assert self._retriever is not None
        assert self._chunks is not None
        assert self._stemmer is not None

        q_tokens = bm25s.tokenize([query], stemmer=self._stemmer)
        indices, scores = self._retriever.retrieve(q_tokens, k=min(top_k, len(self._chunks)))

        results: list[dict[str, Any]] = []
        for idx, score in zip(indices[0], scores[0]):
            if score <= 0:
                continue
            chunk = self._chunks[int(idx)]
            doc_id = chunk["parent_page_id"]
            heading = chunk.get("heading_path", [])
            if isinstance(heading, list):
                heading = " > ".join(heading)
            metadata = {
                "file": doc_id,
                "chunk_id": chunk.get("chunk_id", ""),
                "page_title": chunk.get("page_title", ""),
                "heading_path": heading,
                "stratum": chunk.get("stratum", ""),
                "sub_stratum": chunk.get("sub_stratum", ""),
            }
            results.append({
                "content": chunk["text"],
                "source": doc_id,
                "metadata": metadata,
                "score": float(score),
            })
        return results

    def embed(self, text: str) -> list[float] | None:
        return None

    @property
    def available_modes(self) -> list[str]:
        return ["lexical"]

    def get_params(self) -> dict[str, Any]:
        self._ensure_index()
        assert self._chunks is not None
        return {
            "k1": self._k1,
            "b": self._b,
            "stemmer": "snowball_english",
            "chunks_path": self._chunks_path,
            "num_chunks": len(self._chunks),
        }

    def __getstate__(self) -> dict[str, Any]:
        return {"chunks_path": self._chunks_path, "k1": self._k1, "b": self._b}

    def __setstate__(self, state: dict[str, Any]) -> None:
        self._chunks_path = state["chunks_path"]
        self._k1 = state["k1"]
        self._b = state["b"]
        self._chunks = None
        self._retriever = None
        self._stemmer = None
