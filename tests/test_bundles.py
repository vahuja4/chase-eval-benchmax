"""Tests for per-backend bundle resolution (src/bundles.py)."""

import json

import pytest

from src import bundles
from src.bundles import bundle_dir, require_bundle, search_backend


def test_default_backend_is_local(monkeypatch):
    monkeypatch.delenv("SEARCH_BACKEND", raising=False)
    assert search_backend() == "local"


def test_env_var_selects_backend(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "postgres")
    assert search_backend() == "postgres"
    assert bundle_dir().name == "postgres"


def test_explicit_arg_beats_env_var(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "postgres")
    assert search_backend("local") == "local"


def test_unknown_backend_rejected(monkeypatch):
    monkeypatch.setenv("SEARCH_BACKEND", "castform")
    with pytest.raises(ValueError, match="castform"):
        search_backend()


def _write_bundle(directory, stem, backend_stamp):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{stem}_cls.pkl").write_bytes(b"fake")
    (directory / f"{stem}_metadata.json").write_text(
        json.dumps({"search_backend": backend_stamp})
    )


def test_require_bundle_returns_verified_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES_ROOT", tmp_path)
    _write_bundle(tmp_path / "local", "linker_env", "local")
    pkl, meta = require_bundle("linker_env", "local")
    assert pkl == tmp_path / "local" / "linker_env_cls.pkl"
    assert meta == tmp_path / "local" / "linker_env_metadata.json"


def test_require_bundle_missing_gives_rebuild_hint(tmp_path, monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES_ROOT", tmp_path)
    with pytest.raises(FileNotFoundError, match="SEARCH_BACKEND=postgres python build_env_bundle.py"):
        require_bundle("linker_env", "postgres")


def test_require_bundle_stamp_mismatch_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(bundles, "BUNDLES_ROOT", tmp_path)
    _write_bundle(tmp_path / "postgres", "env", "local")
    with pytest.raises(ValueError, match="stamped search_backend='local'"):
        require_bundle("env", "postgres")


def test_real_local_bundles_resolve():
    """The checked-in local bundle set must satisfy the resolver."""
    for stem in ("env", "linker_env"):
        pkl, meta = require_bundle(stem, "local")
        assert pkl.stat().st_size > 0
        assert json.loads(meta.read_text())["search_backend"] == "local"
